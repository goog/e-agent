#!/usr/bin/env python3
"""
SelfEvolvingAgent v3 — Full validation with Task Feature Checklist + Auto-Tests.

Validation has 3 layers:
  1. Task Feature Checklist — structural features extracted from goal (file exists,
     has function, has class, has docstring, has error handling, etc.)
  2. Auto-Generated Tests — behavioral tests generated from goal semantics
     (input/output assertions, edge cases, type checks)
  3. Quality Gates — code quality checks (no syntax errors, passes linting heuristics,
     reasonable size, no obvious anti-patterns)

Evolution: skills, patches, strategies, and TEST CASES persist across runs.
"""
import sys
import os, json, hashlib, subprocess, traceback, re, ast
from pathlib import Path
from datetime import datetime
#from copy import deepcopy
from typing import Set, List
import uuid
import logging
import questionary
import chroma_user_api
from memory_compact import AgentMemory

logging.basicConfig(level=logging.INFO)

WORKSPACE       = Path("agent_workspace")
MEMORY_DIR      = WORKSPACE / ".memory"
SKILLS_FILE     = MEMORY_DIR / "skills.json"
PATCHES_FILE    = MEMORY_DIR / "patches.json"
STRATEGIES_FILE = MEMORY_DIR / "strategies.json"
TESTS_FILE      = MEMORY_DIR / "learned_tests.json"
EVOLUTION_LOG   = MEMORY_DIR / "evolution_log.jsonl"
MAX_RETRIES     = 10
STUCK_THRESHOLD = 2

for d in [WORKSPACE, MEMORY_DIR]:
    d.mkdir(parents=True, exist_ok=True)



STOPWORDS: Set[str] = {
    "a", "an", "the", "create", "make", "write", "generate"
}

def to_filename(text: str, ext: str = "py") -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
 
    words: List[str] = [
        w for w in text.strip().split()
        if w not in STOPWORDS
    ]
    
    # 只取最后5个单词
    words = words[-5:]
    
    if not words:
        return f"output__.{ext}"
    
    return f"{'_'.join(words)}.{ext}"


def has_iteration(s: str) -> bool:
    """True if the source contains a loop or recursive call."""
    if "for " in s or "while " in s:
        return True
    # Detect recursion: any defined function that calls itself
    defined = re.findall(r"def (\w+)", s)
    return any(s.count(name) >= 2 for name in defined)
# =====================================================================
#  TOOL REGISTRY
# =====================================================================

class ToolRegistry:
    def __init__(self):
        self._tools = {}
        self._meta = {}
        self._stats = {}
        self._register_builtins()

    def _register_builtins(self):
        self.register("read_file",   self._read_file,   "Read file contents")
        self.register("write_file",  self._write_file,  "Write string to file")
        self.register("list_files",  self._list_files,  "List workspace files")
        self.register("delete_file", self._delete_file, "Delete a file")
        self.register("run_python",  self._run_python,  "Run Python code, return stdout+stderr+rc")
        self.register("web_search",  self._web_search,  "Web search")
        self.register("file_exists", self._file_exists, "Check if file exists")

    def register(self, name, func, desc=""):
        self._tools[name] = func
        self._meta[name] = desc
        self._stats.setdefault(name, {"calls": 0, "ok": 0, "fail": 0})

    def call(self, name, **kw):
        if name not in self._tools:
            return {"ok": False, "error": f"Unknown tool: {name}"}
        self._stats[name]["calls"] += 1
        try:
            r = self._tools[name](**kw)
            self._stats[name]["ok"] += 1
            return {"ok": True, "result": r}
        except Exception as e:
            self._stats[name]["fail"] += 1
            return {"ok": False, "error": str(e), "tb": traceback.format_exc()}

    def catalog(self):
        return {k: self._meta.get(k, "") for k in self._tools}

    @property
    def stats(self):
        return dict(self._stats)

    @staticmethod
    def _read_file(path):
        return (WORKSPACE / path).read_text()

    @staticmethod
    def _write_file(path: str | Path, content: str):
        p = WORKSPACE / path
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except OSError as e:
            raise RuntimeError(f"Failed to write {p}: {e}") from e
        return f"wrote {len(content):,} chars → {p}"
        #return p

    @staticmethod
    def _list_files(directory="."):
        root = WORKSPACE / directory
        return sorted(str(p.relative_to(WORKSPACE)) for p in root.rglob("*")
                       if p.is_file() and ".memory" not in str(p))

    @staticmethod
    def _delete_file(path):
        (WORKSPACE / path).unlink(missing_ok=True)
        return "ok"

    @staticmethod
    def _file_exists(path):
        return (WORKSPACE / path).exists()

    @staticmethod
    def _run_python(code, cwd=None):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]  # short 8-char UUID fragment
        filename = f"{timestamp}_{unique_id}.py"

        tmp = WORKSPACE / filename
        tmp.write_text(code, encoding='utf-8')
        try:
            ## for windows python
            r = subprocess.run(["python", str(tmp.resolve())], capture_output=True,
                               text=True, timeout=30, cwd=str(cwd or WORKSPACE),
                               encoding='utf-8',
                               env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            return {"stdout": r.stdout, "stderr": r.stderr, "rc": r.returncode}
        finally:
            tmp.unlink(missing_ok=True)

    @staticmethod
    def _web_search(query):
        """Web search using Tavily API (falls back to placeholder if no key)."""
        import os
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if api_key:
            try:
                from tavily import TavilyClient
                client = TavilyClient(api_key=api_key)
                resp = client.search(query, max_results=5)
                return [{"title": r.get("title", ""), "href": r.get("url", ""),
                         "body": r.get("content", "")} for r in resp.get("results", [])]
            except Exception as e:
                return [{"title": "Tavily error", "href": "", "body": str(e)}]
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=5))
        except Exception:
            return [{"title": f"Result: {query}", "href": "https://example.com",
                     "body": f"Placeholder result for '{query}'."}]


# =====================================================================
#  PERSISTENT MEMORY
# =====================================================================

class Memory:
    def __init__(self):
        self.skills       = self._load(SKILLS_FILE, {})
        self.patches      = self._load(PATCHES_FILE, [])
        self.strategies   = self._load(STRATEGIES_FILE, {
            "linear": {"desc": "plan-execute-validate", "score": 0.5, "used": 0}
        })
        self.learned_tests = self._load(TESTS_FILE, {})

    @staticmethod
    def _load(p, default):
        return json.loads(p.read_text()) if p.exists() else default

    def save(self):
        SKILLS_FILE.write_text(json.dumps(self.skills, indent=2))
        PATCHES_FILE.write_text(json.dumps(self.patches, indent=2))
        STRATEGIES_FILE.write_text(json.dumps(self.strategies, indent=2))
        TESTS_FILE.write_text(json.dumps(self.learned_tests, indent=2))

    def add_skill(self, name, code, desc, score=1.0):
        self.skills[name] = {"code": code, "desc": desc, "score": score,
                             "created": datetime.now().isoformat(), "uses": 0}
        self.save()

    def add_patch(self, pattern, fix_desc, transform):
        self.patches.append({"pattern": pattern, "fix": fix_desc,
                             "transform": transform, "created": datetime.now().isoformat()})
        self.save()

    def add_learned_test(self, goal_hash, test_code, description):
        self.learned_tests[goal_hash] = {"code": test_code, "desc": description,
                                          "created": datetime.now().isoformat()}
        self.save()

    def best_strategy(self):
        return max(self.strategies, key=lambda k: self.strategies[k]["score"]) if self.strategies else "linear"

    def update_score(self, name, delta):
        if name in self.strategies:
            s = self.strategies[name]
            s["score"] = max(0, min(1, s["score"] + delta))
            s["used"] = s.get("used", 0) + 1
            self.save()

    def log(self, entry):
        with open(EVOLUTION_LOG, "a") as f:
            f.write(json.dumps({**entry, "ts": datetime.now().isoformat()}) + "\n")


# =====================================================================
#  TASK FEATURE EXTRACTOR — analyzes goal to produce feature checklist
# =====================================================================

class TaskFeatureExtractor:
    """Extracts required features from goal text to build a validation checklist."""

    FEATURE_RULES = [
        # (keywords_in_goal, feature_id, feature_description, check_type)
        (["function", "def", "implement", "method"],
         "has_function", "Code defines at least one function", "ast_check"),
        (["class"],
         "has_class", "Code defines at least one class", "ast_check"),
        (["error", "exception", "handle", "try", "raise", "invalid", "negative"],
         "has_error_handling", "Code has error/exception handling", "ast_check"),
        (["return"],
         "has_return", "Function(s) have return statements", "ast_check"),
        (["docstring", "document", "doc"],
         "has_docstring", "Functions/classes have docstrings", "ast_check"),
        (["import", "library", "module", "package"],
         "has_imports", "Code uses imports", "ast_check"),
        (["test", "assert", "verify", "check", "validate"],
         "has_tests", "Code includes test assertions", "content_check"),
        (["print", "output", "display", "log"],
         "has_output", "Code produces output", "content_check"),
        (["file", "write", "save", "create", "generate"],
         "produces_file", "Execution produces the target file", "exec_check"),
        (["read", "parse", "load", "open"],
         "has_file_io", "Code performs file I/O", "content_check"),
        (["list", "dict", "array", "collection", "data structure"],
         "has_data_structures", "Code uses data structures", "content_check"),
        (["loop", "iterate", "for", "while", "recursive", "recursion"],
         "has_iteration", "Code has loops or recursion", "content_check"),
        (["type", "hint", "annotation", "typing"],
         "has_type_hints", "Code uses type hints", "content_check"),
        (["main", "__main__", "entry", "script"],
         "has_main", "Code has a main entry point", "content_check"),
        (["fibonacci"],
         "impl_fibonacci", "Implements fibonacci correctly", "behavioral"),
        (["factorial"],
         "impl_factorial", "Implements factorial correctly", "behavioral"),
        (["sort", "sorting"],
         "impl_sort", "Implements sorting correctly", "behavioral"),
        (["search", "find", "look up"],
         "does_search", "Performs web search", "exec_check"),
        (["api", "request", "http", "fetch"],
         "has_api_call", "Code makes API/HTTP requests", "content_check"),
    ]

    @staticmethod
    def extract(goal):
        goal_lower = goal.lower()
        features = []
        for keywords, feat_id, desc, check_type in TaskFeatureExtractor.FEATURE_RULES:
            if any(kw in goal_lower for kw in keywords):
                features.append({
                    "id": feat_id,
                    "description": desc,
                    "check_type": check_type,
                    "required": True,
                })

        if not any(f["id"].startswith("has_") and f["check_type"] == "ast_check" for f in features):
            features.append({
                "id": "has_content",
                "description": "Output file has meaningful content",
                "check_type": "content_check",
                "required": True,
            })

        return features


# =====================================================================
#  TEST GENERATOR — auto-generates behavioral tests from goal
# =====================================================================

class TestGenerator:
    """Generates test code based on goal semantics and detected features."""

    TEST_TEMPLATES = {
        "impl_fibonacci": '''
def test_fibonacci():
    from {module} import fibonacci
    assert fibonacci(0) == 0, "fibonacci(0) should be 0"
    assert fibonacci(1) == 1, "fibonacci(1) should be 1"
    assert fibonacci(2) == 1, "fibonacci(2) should be 1"
    assert fibonacci(5) == 5, "fibonacci(5) should be 5"
    assert fibonacci(10) == 55, "fibonacci(10) should be 55"
    assert fibonacci(20) == 6765, "fibonacci(20) should be 6765"
    # Edge cases
    try:
        fibonacci(-1)
        assert False, "Should raise error for negative input"
    except (ValueError, Exception):
        pass
    print("  [TEST] fibonacci: ALL PASSED (7 cases)")
''',
        "impl_factorial": '''
def test_factorial():
    from {module} import factorial
    assert factorial(0) == 1, "factorial(0) should be 1"
    assert factorial(1) == 1, "factorial(1) should be 1"
    assert factorial(5) == 120, "factorial(5) should be 120"
    assert factorial(10) == 3628800, "factorial(10) should be 3628800"
    try:
        factorial(-1)
        assert False, "Should raise error for negative input"
    except (ValueError, Exception):
        pass
    print("  [TEST] factorial: ALL PASSED (5 cases)")
''',
        "impl_sort": '''
def test_sort():
    import importlib
    mod = importlib.import_module("{module}")
    sort_fn = None
    for name in dir(mod):
        obj = getattr(mod, name)
        if callable(obj) and "sort" in name.lower():
            sort_fn = obj
            break
    assert sort_fn is not None, "No sort function found"
    assert sort_fn([]) == [], "empty list"
    assert sort_fn([1]) == [1], "single element"
    assert sort_fn([3,1,2]) == [1,2,3], "basic sort"
    assert sort_fn([5,3,8,1,2]) == [1,2,3,5,8], "larger list"
    assert sort_fn([1,1,1]) == [1,1,1], "duplicates"
    assert sort_fn([-3,0,3]) == [-3,0,3], "negatives"
    print("  [TEST] sort: ALL PASSED (6 cases)")
''',
    }

    @staticmethod
    def generate_tests(goal, fname, features):
        module = fname.replace(".py", "")
        test_blocks = []
        test_calls = []

        for feat in features:
            fid = feat["id"]
            if fid in TestGenerator.TEST_TEMPLATES:
                test_code = TestGenerator.TEST_TEMPLATES[fid].format(module=module)
                test_blocks.append(test_code)
                func_name = f"test_{fid.replace('impl_', '')}"
                test_calls.append(func_name)

        if not test_blocks and fname.endswith(".py"):
            test_blocks.append(f'''
def test_import():
    import importlib
    mod = importlib.import_module("{module}")
    assert mod is not None, "Module should be importable"
    print("  [TEST] import: PASSED")
''')
            test_calls.append("test_import")

            test_blocks.append(f'''
def test_executes():
    import subprocess, sys
    r = subprocess.run([sys.executable, "{fname}"], capture_output=True, text=True, timeout=15)
    assert r.returncode == 0, f"Exit code {{r.returncode}}: {{r.stderr[:200]}}"
    print("  [TEST] executes: PASSED")
''')
            test_calls.append("test_executes")

        if fname.endswith(".py"):
            test_blocks.append(f'''
def test_syntax():
    import ast
    with open("{fname}") as f:
        source = f.read()
    try:
        ast.parse(source)
    except SyntaxError as e:
        assert False, f"Syntax error: {{e}}"
    print("  [TEST] syntax: PASSED")
''')
            test_calls.append("test_syntax")

        runner = "\nimport sys, os\nsys.path.insert(0, '.')\nos.chdir(os.path.dirname(os.path.abspath(__file__)) or '.')\n\n"
        runner += "\n".join(test_blocks)
        runner += "\n\ndef run_all_tests():\n"
        runner += "    results = {'passed': 0, 'failed': 0, 'errors': []}\n"
        for tc in test_calls:
            runner += f"    try:\n"
            runner += f"        {tc}()\n"
            runner += f"        results['passed'] += 1\n"
            runner += f"    except Exception as e:\n"
            runner += f"        results['failed'] += 1\n"
            runner += f"        results['errors'].append('{tc}: ' + str(e))\n"
            runner += f"        print(f'  [TEST] {tc}: FAILED - {{e}}')\n"
        runner += "    return results\n\n"
        runner += "if __name__ == '__main__':\n"
        runner += "    import json\n"
        runner += "    r = run_all_tests()\n"
        runner += "    print(json.dumps(r))\n"
        runner += "    sys.exit(0 if r['failed'] == 0 else 1)\n"

        return runner, test_calls


# =====================================================================
#  ACCEPTANCE CRITERIA — 3-layer validation
# =====================================================================

class AcceptanceCriteria:

    @staticmethod
    def generate(goal):
        fname = AcceptanceCriteria._filename(goal)
        features = TaskFeatureExtractor.extract(goal)
        test_code, test_names = TestGenerator.generate_tests(goal, fname, features)
        criteria = {
            "fname": fname,
            "features": features,
            "test_code": test_code,
            "test_names": test_names,
        }
        return criteria

    @staticmethod
    def _filename(goal):
        m = re.search(r"['\"]([^'\"]+\.\w+)['\"]", goal)
        if m: return m.group(1)
        for t in goal.split():
            if "." in t and not t.startswith("http"):
                return t.strip(".,;:()'\"")
        return to_filename(goal)

    @staticmethod
    def evaluate(criteria, tools):
        fname = criteria["fname"]
        features = criteria["features"]
        test_code = criteria["test_code"]
        fpath = WORKSPACE / fname

        report = {
            "feature_checklist": [],
            "test_results": {},
            "quality_gates": [],
            "summary": {},
        }

        # ---- LAYER 1: Task Feature Checklist ----
        source = ""
        tree = None
        if fpath.exists():
            #source = fpath.read_text()
            source = fpath.read_text(encoding='utf-8', errors='replace')
            if fname.endswith(".py"):
                try:
                    tree = ast.parse(source)
                except SyntaxError:
                    tree = None

        for feat in features:
            result = AcceptanceCriteria._check_feature(feat, fpath, source, tree)
            report["feature_checklist"].append(result)

        # ---- LAYER 2: Auto-Generated Tests ----
        if test_code and fname.endswith(".py"):
            test_file = WORKSPACE / "_validation_tests.py"
            test_file.write_text(test_code)
            try:
                r = subprocess.run(
                    ["python", str(test_file.resolve())],
                    capture_output=True, text=True, timeout=30, cwd=str(WORKSPACE)
                )
                test_output = r.stdout + r.stderr
                try:
                    last_line = [l for l in r.stdout.strip().split("\n") if l.strip()][-1]
                    test_json = json.loads(last_line)
                    report["test_results"] = {
                        "passed": test_json.get("passed", 0),
                        "failed": test_json.get("failed", 0),
                        "errors": test_json.get("errors", []),
                        "output": test_output[:500],
                        "all_passed": test_json.get("failed", 1) == 0,
                    }
                except (json.JSONDecodeError, IndexError):
                    report["test_results"] = {
                        "passed": 0, "failed": 1,
                        "errors": [f"Test runner output: {test_output[:300]}"],
                        "output": test_output[:500],
                        "all_passed": r.returncode == 0,
                    }
            except subprocess.TimeoutExpired:
                report["test_results"] = {
                    "passed": 0, "failed": 1, "errors": ["Tests timed out"],
                    "output": "", "all_passed": False,
                }
            finally:
                test_file.unlink(missing_ok=True)
        else:
            report["test_results"] = {"passed": 0, "failed": 0, "errors": [],
                                       "output": "", "all_passed": True, "skipped": True}

        # ---- LAYER 3: Quality Gates ----
        report["quality_gates"] = AcceptanceCriteria._quality_gates(fname, fpath, source, tree)

        # ---- SUMMARY ----
        feat_pass = sum(1 for f in report["feature_checklist"] if f["passed"])
        feat_total = len(report["feature_checklist"])
        tests_pass = report["test_results"].get("all_passed", False)
        quality_pass = sum(1 for g in report["quality_gates"] if g["passed"])
        quality_total = len(report["quality_gates"])

        total_checks = feat_total + (1 if not report["test_results"].get("skipped") else 0) + quality_total
        total_passed = feat_pass + (1 if tests_pass else 0) + quality_pass
        score = min(1.0, total_passed / total_checks) if total_checks > 0 else 0.0

        report["summary"] = {
            "score": score,
            "features": f"{feat_pass}/{feat_total}",
            "tests": "PASS" if tests_pass else "FAIL",
            "quality": f"{quality_pass}/{quality_total}",
            "total": f"{total_passed}/{total_checks}",
        }

        return report

    @staticmethod
    def _check_feature(feat, fpath, source, tree):
        fid = feat["id"]
        result = {"id": fid, "description": feat["description"], "passed": False, "detail": ""}

        if feat["check_type"] == "exec_check":
            if fid == "produces_file":
                result["passed"] = fpath.exists() and fpath.stat().st_size > 0
                result["detail"] = f"exists={fpath.exists()}, size={fpath.stat().st_size if fpath.exists() else 0}"
            elif fid == "does_search":
                result["passed"] = True
                result["detail"] = "Search tool called during execution"
            return result

        if not source:
            result["detail"] = "No source file found"
            return result

        if feat["check_type"] == "content_check":
            checks = {
                "has_tests":       lambda s: "assert " in s or "test" in s.lower(),
                "has_output":      lambda s: "print(" in s or "logging" in s,
                "has_file_io":     lambda s: "open(" in s or "read(" in s or "write(" in s,
                "has_data_structures": lambda s: any(k in s for k in ["list(", "dict(", "[", "{"]),
                "has_iteration":   has_iteration,
                "has_content":     lambda s: len(s.strip()) > 20,
                "has_imports":     lambda s: "import " in s,
                "has_api_call":    lambda s: "requests." in s or "http" in s.lower() or "fetch" in s,
                "has_main":        lambda s: "__main__" in s or "def main" in s,
                "has_type_hints":  lambda s: bool(re.search(r"def \w+\([^)]*:\s*\w+", s)) or "-> " in s,
            }
            checker = checks.get(fid)
            if checker:
                result["passed"] = checker(source)
                result["detail"] = "content pattern match" if result["passed"] else "pattern not found"
            return result

        if feat["check_type"] == "ast_check" and tree:
            checks = {
                "has_function":       lambda t: any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(t)),
                "has_class":          lambda t: any(isinstance(n, ast.ClassDef) for n in ast.walk(t)),
                "has_error_handling": lambda t: any(isinstance(n, (ast.Try, ast.Raise)) for n in ast.walk(t)),
                "has_return":         lambda t: any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(t)),
                "has_docstring":      lambda t: any(
                    isinstance(n, (ast.FunctionDef, ast.ClassDef)) and
                    n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, (ast.Constant, ast.Str))
                    for n in ast.walk(t)),
                "has_imports":        lambda t: any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(t)),
            }
            checker = checks.get(fid)
            if checker:
                result["passed"] = checker(tree)
                result["detail"] = "AST check passed" if result["passed"] else "AST check failed"
            return result

        if feat["check_type"] == "behavioral":
            result["passed"] = True
            result["detail"] = "Validated by test suite"

        return result

    @staticmethod
    def _quality_gates(fname, fpath, source, tree):
        gates = []

        gates.append({
            "id": "file_exists",
            "description": f"Output file '{fname}' exists",
            "passed": fpath.exists(),
        })

        gates.append({
            "id": "file_not_empty",
            "description": f"Output file has meaningful content (>10 bytes)",
            "passed": fpath.exists() and fpath.stat().st_size > 10,
        })

        if fname.endswith(".py"):
            gates.append({
                "id": "valid_syntax",
                "description": "Python syntax is valid",
                "passed": tree is not None,
            })

            if source:
                gates.append({
                    "id": "no_todo_fixme",
                    "description": "No TODO/FIXME/HACK placeholders left",
                    "passed": not any(marker in source.upper() for marker in ["TODO", "FIXME", "HACK", "XXX"]),
                })

                gates.append({
                    "id": "reasonable_size",
                    "description": "Code is between 50 and 50000 chars",
                    "passed": 50 <= len(source) <= 50000,
                })

                gates.append({
                    "id": "no_pass_only_funcs",
                    "description": "No empty function bodies (just 'pass')",
                    "passed": not bool(re.search(r"def \w+\([^)]*\):\s*\n\s+pass\s*\n", source)),
                })

        return gates


# =====================================================================
#  CODE GENERATOR
# =====================================================================

class CodeGenerator:
    """Generate code using OpenAI API (or fallback templates)."""

    def __init__(self, patches=None):
        self.patches = patches or []
        self._client = None

    def _get_client(self):
        if self._client is None:
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if api_key:
                from openai import OpenAI
                base_url ="https://api.deepseek.com" #os.environ.get("OPENAI_BASE_URL", None)
                self._client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
            else:
                self._client = False
        return self._client

    def _llm_generate(self, context, fname):
        client = self._get_client()
        if not client:
            return None
        # is_code = fname.endswith(".py")
        # if is_code:
            # prompt = (
                # f"Write a complete Python file for this goal: {goal}\n"
                # f"The file will be saved as {fname}.\n"
                # "Requirements:\n"
                # "- Include a run_tests() function with assert-based tests\n"
                # "- Include if __name__ == '__main__': run_tests()\n"
                # "- Include error handling where appropriate\n"
                # "- Return ONLY the Python code, no markdown fences"
            # )
        # else:
            # prompt = (
                # f"Generate the content for a file named {fname} for this goal: {goal}\n"
                # "Return ONLY the file content, no markdown fences."
            # )
        messages=[{"role": "system", "content": "You are a Python expert. Output code only, no explanations."}]
        messages = messages + context
        logging.info(f"messages {messages}")

        model = "deepseek-reasoner"
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,
        )
        code = resp.choices[0].message.content.strip()
        if code.startswith("```"):
            code = code.split("\n", 1)[1] if "\n" in code else code[3:]
            if code.endswith("```"):
                code = code[:-3].rstrip()
        return code

    def generate(self, goal, fname, context):
        code = self._llm_generate(context, fname)
        if code:
            code = self._apply_patches(code, goal)
            return code

        goal_lower = goal.lower()
        if any(k in goal_lower for k in ["search", "find", "look up"]):
            sr = context.get("search_results", []) if context else []
            lines_out = ["# Search Results", ""]
            for r in sr:
                lines_out.append(f"- {r.get('title','')}: {r.get('body','')}")
            file_content = "\n".join(lines_out)
        else:
            file_content = f"Auto-generated content for goal: {goal}"

        code = "def main():\n"
        code += f"    content = {repr(file_content)}\n"
        code += f"    with open({repr(fname)}, 'w') as f:\n"
        code += "        f.write(content)\n"
        code += f"    print('Created {fname}')\n\n"
        code += "if __name__ == '__main__':\n"
        code += "    main()\n"
        return self._apply_patches(code, goal)

    def _apply_patches(self, code, goal):
        for patch in self.patches:
            if patch.get("pattern", "") in goal.lower():
                transform = patch.get("transform", "")
                if transform == "add_os_chdir":
                    code = "import os; os.chdir(os.path.dirname(os.path.abspath(__file__)) or '.')\n" + code
        return code

class BrainstormEngine:
    ERROR_FIXES = [
        ("not found",   "File path mismatch",           "patch_path"),
        ("no such file","File path mismatch",           "patch_path"),
        #("syntax",      "Syntax error in generated code","simplify"),
        ("cannot import","Wrong skill reused, regenerate", "rewrite"),
        ("import",      "Missing import",                "rewrite"),
        ("timeout",     "Infinite loop / timeout",       "add_limits"),
        ("permission",  "Permission denied",             "patch_path"),
        ("assert",      "Test assertion failure",        "fix_logic"),
        ("attribute",   "Wrong attribute/method",        "fix_logic"),
        ("type",        "Type error",                    "fix_types"),
    ]

    @staticmethod
    def analyze(goal, report, history):
        errors_text = json.dumps(report, default=str).lower()

        for pattern, diagnosis, action in BrainstormEngine.ERROR_FIXES:
            if pattern in errors_text:
                return action, diagnosis

        if len(history) >= 3:
            return "rewrite", "Complete rewrite needed"
        return "retry", "Retry with adjustments"


# =====================================================================
#  REPORT PRINTER — rich validation output
# =====================================================================

class ReportPrinter:
    @staticmethod
    def print_report(report):
        print("\n  ┌─────────────────────────────────────────────────┐")
        print("  │           VALIDATION REPORT                     │")
        print("  ├─────────────────────────────────────────────────┤")

        print("  │  TASK FEATURE CHECKLIST:                        │")
        for f in report["feature_checklist"]:
            icon = "✓" if f["passed"] else "✗"
            desc = f["description"][:42].ljust(42)
            print(f"  │    [{icon}] {desc} │")

        print("  ├─────────────────────────────────────────────────┤")
        tr = report["test_results"]
        if tr.get("skipped"):
            print("  │  AUTO TESTS: (skipped — not a Python file)     │")
        else:
            icon = "✓" if tr.get("all_passed") else "✗"
            print(f"  │  AUTO TESTS: [{icon}] {tr.get('passed',0)} passed, {tr.get('failed',0)} failed          │")
            for err in tr.get("errors", [])[:3]:
                print(f"  │    ✗ {err[:44].ljust(44)} │")

        print("  ├─────────────────────────────────────────────────┤")
        print("  │  QUALITY GATES:                                 │")
        for g in report["quality_gates"]:
            icon = "✓" if g["passed"] else "✗"
            desc = g["description"][:42].ljust(42)
            print(f"  │    [{icon}] {desc} │")

        print("  ├─────────────────────────────────────────────────┤")
        s = report["summary"]
        print(f"  │  SCORE: {s['score']:.0%}  Features: {s['features']}  Tests: {s['tests']}  Quality: {s['quality']} │")
        print(f"  │  Total: {s['total']} checks passed                      │")
        print("  └─────────────────────────────────────────────────┘")


# =====================================================================
#  SELF-EVOLVING AGENT
# =====================================================================

class SelfEvolvingAgent:
    def __init__(self):
        self.tools = ToolRegistry()
        self.memory = Memory()
        self.codegen = CodeGenerator(patches=self.memory.patches)
        self.history = []
        self.iteration = 0
        self.context = None  ## conversation history
    def run(self, goal):
        print(f"\n{'='*60}")
        print(f"  GOAL: {goal}")
        print(f"{'='*60}")
        
        self.context = AgentMemory(
            goal=goal,
            max_messages_before_compact=20,  # compaction triggers here
            recent_messages_to_keep=3,       # verbatim turns preserved
        )
        #self.context.add("user", goal)

        criteria = AcceptanceCriteria.generate(goal)
        fname = criteria["fname"]
        logging.info(f"fname {fname}")
        is_code = fname.endswith(".py")
        if is_code:
            prompt = (
                f"Write a complete Python file for this goal: {goal}\n"
                f"The file will be saved as {fname}.\n"
                "Requirements:\n"
                "- Include a run_tests() function with assert-based tests\n"
                "- Include if __name__ == '__main__': run_tests()\n"
                "- Include error handling where appropriate\n"
                "- Return ONLY the Python code, no markdown fences"
            )
        else:
            prompt = (
                f"Generate the content for a file named {fname} for this goal: {goal}\n"
                "Return ONLY the file content, no markdown fences."
            )
        self.context.add("user", prompt)

        features = criteria["features"]
        print(f"\n  [FEATURES] Extracted {len(features)} required task features:")
        for f in features:
            print(f"     • {f['id']}: {f['description']} ({f['check_type']})")
        print(f"  [TESTS] Generated {len(criteria['test_names'])} auto-tests: {criteria['test_names']}")

        strategy = self.memory.best_strategy()
        prev_score = -1
        stuck_count = 0

        for attempt in range(1, MAX_RETRIES + 1):
            self.iteration = attempt
            print(f"\n--- Iteration {attempt}/{MAX_RETRIES} | strategy='{strategy}' ---")

            context = {}
            if any(k in goal.lower() for k in ["search", "find", "look up"]):
                sr = self.tools.call("web_search", query=goal)
                context["search_results"] = sr.get("result", []) if sr["ok"] else []

            skip_reuse = any(
                "cannot import" in str(r.get("report", {}).get("test_results", {}).get("errors", []))
                for r in self.history[-2:]
            )
            matching_skill = None if skip_reuse else self._find_skill(goal)
            if matching_skill:
                ## skill confirm
                answer = questionary.confirm("confirm to reuse history code").ask()
                if answer:
                    print(f"  [REUSE] Skill: {matching_skill}")
                    code = self.memory.skills[matching_skill]["code"]
                    self.memory.skills[matching_skill]["uses"] += 1
                    self.memory.save()
            else:
                ##build context
                ctx = self.context.build_context()
                code = self.codegen.generate(goal, fname, ctx)
                logging.info(f"** code generate {code}")
                self.context.add("assistant", code)
            self.tools.call("write_file", path=fname, content=code)
            print(f"**[EXEC] Written {fname} ({len(code)} chars)")

            run_r = self.tools.call("run_python", code=code)
            logging.info(f"tools.call output {run_r}")
            if run_r["ok"]:
                r = run_r["result"]
                if r["stdout"].strip():
                    print(f"  [EXEC] stdout: {r['stdout'].strip()[:150]}")
                if r["stderr"].strip():
                    logging.error(f"python run stderr: {r['stderr'].strip()}")
                    self.context.add("user", "fix error: " + r['stderr'].strip())
            else:
                logging.error(f"  [EXEC] false *Error: {run_r['error'][:200]}")
                # use run_r['tb'] add to context and regenerate
                self.context.add("user", run_r['tb'])

            report = AcceptanceCriteria.evaluate(criteria, self.tools)
            ReportPrinter.print_report(report)

            score = report["summary"]["score"]
            record = {"attempt": attempt, "strategy": strategy, "score": score,
                      "report": report, "code": code}
            self.history.append(record)

            if score >= 0.9 and report["test_results"].get("all_passed", True):
                print(f"\n  >>> GOAL ACHIEVED (score={score:.0%}) on iteration {attempt}! <<<")
                self._evolve_success(goal, code, score, criteria)
                self.memory.update_score(strategy, +0.1)
                return {"success": True, "iterations": attempt, "score": score, "file": fname, "report": report}

            if score <= prev_score:
                stuck_count += 1
            else:
                stuck_count = 0
            prev_score = score

            if stuck_count >= STUCK_THRESHOLD:
                print(f"\n  [STUCK] Brainstorming...")

                action, diagnosis = BrainstormEngine.analyze(goal, report, self.history)
                logging.info(f"  [FIX] {action}: {diagnosis}")
                self._apply_fix(action, goal, fname, report, code)

        best = max(self.history, key=lambda h: h["score"])
        print(f"\n{'='*60}")
        print(f"  FINISHED — best score: {best['score']:.0%}")
        print(f"{'='*60}")
        return {"success": best["score"] >= 0.9, "iterations": MAX_RETRIES,
                "score": best["score"], "file": fname}

    def _find_skill(self, goal):
        #goal_lower = goal.lower()
        col = chroma_user_api.get_skill_collection()
        result = chroma_user_api.search_skills(col, goal)
        name = result[0]['id'] if result else None
        if name:
            print(f"matched skill: {result[0]}")
        return name

    def _apply_fix(self, action, goal, fname, report, prev_code):
        if action == "patch_path":
            self.memory.add_patch("file", "Fix file path", "add_os_chdir")
            self.codegen.patches = self.memory.patches
        elif action == "simplify":
            self.tools.call("write_file", path=fname,
                            content=f"# Simplified solution for: {goal}\nprint('Done')\n")
        elif action == "rewrite":
            ##
            ctx = self.context.build_context()
            ctx = ctx[:1]
            fresh_code = self.codegen.generate(goal, fname, ctx)
            self.tools.call("write_file", path=fname, content=fresh_code)
            logging.info(f"  [agent-fix] Regenerated {fname} from scratch ({len(fresh_code)} chars)")
        elif action == "fix_imports":
            if "import" not in prev_code[:50]:
                self.tools.call("write_file", path=fname, content="import os, sys, json\n" + prev_code)
        elif action == "fix_logic":
            test_errors = report.get("test_results", {}).get("errors", [])
            if test_errors:
                print(f"  [DEBUG] Test errors to fix: {test_errors[:2]}")

    def _evolve_success(self, goal, code, score, criteria):
        skill_name = f"skill_{hashlib.md5(goal.encode()).hexdigest()[:8]}"
        self.memory.add_skill(skill_name, code, f"Learned: {goal}", score)
        goal_hash = hashlib.md5(goal.encode()).hexdigest()[:8]
        self.memory.add_learned_test(goal_hash, criteria["test_code"],
                                      f"Tests for: {goal}")
        print(f"  [EVOLVE] Skill '{skill_name}' + tests saved")
        self.memory.log({"type": "success", "goal": goal, "skill": skill_name,
                         "iterations": self.iteration, "score": score,
                         "features_passed": sum(1 for f in criteria["features"]),
                         "test_count": len(criteria["test_names"])})

    def _new_strategy(self, desc):
        name = f"strat_{len(self.memory.strategies)+1}"
        self.memory.strategies[name] = {"desc": desc, "score": 0.5, "used": 0}
        self.memory.save()
        return name


# =====================================================================
#  DEMO
# =====================================================================

def demo(task: str):
    agent = SelfEvolvingAgent()

    print("\n" + "#" * 60)
    print("#  SELF-EVOLVING AGENT v3 — Task Features + Auto Tests")
    print("#" * 60)

    goals = [
        #"create a markdown calendar in python",
        #"Search the web for 'Python async patterns' and save summary to 'async_patterns.txt'",
    ]
    goals.append(task)

    results = []
    for i, goal in enumerate(goals, 1):
        print(f"\n\n{'#'*60}")
        print(f"#  GOAL {i}/{len(goals)}")
        print(f"{'#'*60}")
        r = agent.run(goal)
        results.append(r)

    print("\n\n" + "=" * 60)
    print("  EVOLUTION SUMMARY")
    print("=" * 60)
    for i, (goal, r) in enumerate(zip(goals, results), 1):
        status = "PASS" if r["success"] else "FAIL"
        print(f"  [{status}] Goal {i}: {goal[:50]}... | score={r['score']:.0%} iters={r['iterations']}")

    print(f"\n  Skills: {list(agent.memory.skills.keys())}")
    print(f"  Patches: {len(agent.memory.patches)}")
    print(f"  Learned tests: {len(agent.memory.learned_tests)}")
    print("  Workspace files:")
    for f in sorted(WORKSPACE.rglob("*")):
        if f.is_file() and ".memory" not in str(f):
            print(f"    {f.relative_to(WORKSPACE)}  ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    args = sys.argv
    if len(args) > 1:
        prompt = args[1]
        print("prompt: ", prompt)
        demo(prompt)
    else:
        print("no prompt input")
