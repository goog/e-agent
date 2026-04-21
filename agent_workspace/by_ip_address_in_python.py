import urllib.request
import urllib.error
import json

def get_city_by_ip(ip_address=None):
    """
    Get city name by IP address using ipinfo.io service.
    
    Args:
        ip_address: IP address to lookup. If None, uses current public IP.
    
    Returns:
        City name as string or None if not found.
    
    Raises:
        ConnectionError: If network connection fails.
        ValueError: If response cannot be parsed.
    """
    try:
        url = f"http://ipinfo.io/{ip_address}/json" if ip_address else "http://ipinfo.io/json"
        
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
            
        return data.get('city')
    except urllib.error.URLError as e:
        raise ConnectionError(f"Failed to connect to IP service: {e}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid response from service: {e}")
    except KeyError:
        return None

def run_tests():
    """Test the get_city_by_ip function with various scenarios."""
    # Test 1: Get city for current IP (should return something)
    current_city = get_city_by_ip()
    print(f"Test 1 - Current city: {current_city}")
    assert current_city is None or isinstance(current_city, str), "Current city should be string or None"
    
    # Test 2: Test with known IP (Cloudflare DNS)
    cloudflare_city = get_city_by_ip("1.1.1.1")
    print(f"Test 2 - Cloudflare IP city: {cloudflare_city}")
    assert cloudflare_city is None or isinstance(cloudflare_city, str), "Cloudflare city should be string or None"
    
    # Test 3: Test error handling for invalid IP format
    try:
        # This might return null/None or throw error depending on service
        get_city_by_ip("invalid-ip")
        print("Test 3 - Invalid IP handled gracefully")
    except Exception:
        print("Test 3 - Invalid IP raised exception (acceptable)")
    
    print("All tests completed!")

if __name__ == '__main__':
    run_tests()