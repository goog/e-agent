import argparse
import re
import os
import sys

class TaskManager:
    def __init__(self, filename="tasks.md"):
        self.filename = filename
        self.sections = {
            'incomplete': '## Incomplete Tasks',
            'completed': '## Completed Tasks'
        }
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.filename):
            with open(self.filename, 'w') as f:
                f.write(f"{self.sections['incomplete']}\n\n{self.sections['completed']}\n")

    def _parse_file(self):
        incomplete = []
        completed = []
        current_section = None
        
        try:
            with open(self.filename, 'r') as f:
                for line in f:
                    line = line.rstrip('\n')
                    if line == self.sections['incomplete']:
                        current_section = 'incomplete'
                    elif line == self.sections['completed']:
                        current_section = 'completed'
                    elif line.startswith('- [ ] '):
                        if current_section == 'incomplete':
                            incomplete.append(line[6:])
                    elif line.startswith('- [x] '):
                        if current_section == 'completed':
                            completed.append(line[6:])
        except FileNotFoundError:
            self._ensure_file()
            return [], []
        
        return incomplete, completed

    def _write_file(self, incomplete, completed):
        with open(self.filename, 'w') as f:
            f.write(f"{self.sections['incomplete']}\n")
            for task in incomplete:
                f.write(f"- [ ] {task}\n")
            f.write(f"\n{self.sections['completed']}\n")
            for task in completed:
                f.write(f"- [x] {task}\n")

    def list_tasks(self):
        incomplete, completed = self._parse_file()
        return {
            'incomplete': incomplete,
            'completed': completed
        }

    def add_task(self, description):
        incomplete, completed = self._parse_file()
        incomplete.append(description)
        self._write_file(incomplete, completed)
        return True

    def complete_task(self, index):
        incomplete, completed = self._parse_file()
        try:
            index = int(index)
            if index < 1 or index > len(incomplete):
                return False
            task = incomplete.pop(index-1)
            completed.append(task)
            self._write_file(incomplete, completed)
            return True
        except (ValueError, IndexError):
            return False

    def delete_task(self, section, index):
        incomplete, completed = self._parse_file()
        try:
            index = int(index)
            if section == 'incomplete':
                if index < 1 or index > len(incomplete):
                    return False
                incomplete.pop(index-1)
            elif section == 'completed':
                if index < 1 or index > len(completed):
                    return False
                completed.pop(index-1)
            else:
                return False
            self._write_file(incomplete, completed)
            return True
        except (ValueError, IndexError):
            return False

    def clear_completed(self):
        incomplete, completed = self._parse_file()
        completed.clear()
        self._write_file(incomplete, completed)
        return True

def main():
    parser = argparse.ArgumentParser(description='Manage tasks in markdown file')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # List command
    subparsers.add_parser('list', help='List all tasks')
    
    # Add command
    add_parser = subparsers.add_parser('add', help='Add a new task')
    add_parser.add_argument('description', help='Task description')
    
    # Complete command
    complete_parser = subparsers.add_parser('complete', help='Mark task as complete')
    complete_parser.add_argument('index', type=int, help='Task number to complete')
    
    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete a task')
    delete_parser.add_argument('section', choices=['incomplete', 'completed'], help='Task section')
    delete_parser.add_argument('index', type=int, help='Task number to delete')
    
    # Clear command
    subparsers.add_parser('clear', help='Clear all completed tasks')
    
    args = parser.parse_args()
    manager = TaskManager()
    
    if args.command == 'list':
        tasks = manager.list_tasks()
        print("Incomplete Tasks:")
        for i, task in enumerate(tasks['incomplete'], 1):
            print(f"{i}. {task}")
        print("\nCompleted Tasks:")
        for i, task in enumerate(tasks['completed'], 1):
            print(f"{i}. {task}")
    
    elif args.command == 'add':
        if manager.add_task(args.description):
            print(f"Added: {args.description}")
        else:
            print("Failed to add task")
    
    elif args.command == 'complete':
        if manager.complete_task(args.index):
            print(f"Completed task {args.index}")
        else:
            print("Invalid task number")
    
    elif args.command == 'delete':
        if manager.delete_task(args.section, args.index):
            print(f"Deleted {args.section} task {args.index}")
        else:
            print("Invalid task or section")
    
    elif args.command == 'clear':
        if manager.clear_completed():
            print("Cleared all completed tasks")
        else:
            print("Failed to clear completed tasks")
    
    else:
        parser.print_help()

def run_tests():
    import tempfile
    import shutil
    
    # Setup temporary directory
    test_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    os.chdir(test_dir)
    
    try:
        # Test 1: File creation
        manager = TaskManager("test_tasks.md")
        assert os.path.exists("test_tasks.md")
        
        # Test 2: Add task
        manager.add_task("Test task 1")
        tasks = manager.list_tasks()
        assert tasks['incomplete'] == ["Test task 1"]
        assert tasks['completed'] == []
        
        # Test 3: Complete task
        manager.complete_task(1)
        tasks = manager.list_tasks()
        assert tasks['incomplete'] == []
        assert tasks['completed'] == ["Test task 1"]
        
        # Test 4: Add multiple tasks
        manager.add_task("Test task 2")
        manager.add_task("Test task 3")
        tasks = manager.list_tasks()
        assert tasks['incomplete'] == ["Test task 2", "Test task 3"]
        
        # Test 5: Complete middle task
        manager.complete_task(1)
        tasks = manager.list_tasks()
        assert tasks['incomplete'] == ["Test task 3"]
        assert tasks['completed'] == ["Test task 1", "Test task 2"]
        
        # Test 6: Delete from incomplete
        manager.delete_task('incomplete', 1)
        tasks = manager.list_tasks()
        assert tasks['incomplete'] == []
        
        # Test 7: Delete from completed
        manager.delete_task('completed', 2)
        tasks = manager.list_tasks()
        assert tasks['completed'] == ["Test task 1"]
        
        # Test 8: Clear completed
        manager.clear_completed()
        tasks = manager.list_tasks()
        assert tasks['completed'] == []
        
        # Test 9: Invalid operations
        assert not manager.complete_task(99)
        assert not manager.delete_task('incomplete', 99)
        assert not manager.delete_task('invalid', 1)
        
        print("All tests passed!")
        
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir)

if __name__ == '__main__':
    run_tests()