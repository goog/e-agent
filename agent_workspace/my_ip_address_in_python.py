import json
import socket
import urllib.request
import urllib.error

def get_ip_address():
    """Get the public IP address using multiple fallback services."""
    services = [
        'https://api.ipify.org?format=json',
        'https://api64.ipify.org?format=json',
        'https://httpbin.org/ip'
    ]
    
    for service in services:
        try:
            with urllib.request.urlopen(service, timeout=5) as response:
                data = json.loads(response.read().decode())
                if service == 'https://httpbin.org/ip':
                    ip = data.get('origin')
                else:
                    ip = data.get('ip')
                if ip:
                    return ip
        except (urllib.error.URLError, urllib.error.HTTPError, 
                socket.timeout, json.JSONDecodeError, KeyError):
            continue
    
    try:
        # Fallback to socket-based local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except socket.error:
        return None

def run_tests():
    """Run assertion tests for the IP address functionality."""
    ip = get_ip_address()
    
    # Test 1: IP address should not be None
    assert ip is not None, "Failed to retrieve IP address"
    
    # Test 2: IP address should be a string
    assert isinstance(ip, str), f"IP should be string, got {type(ip)}"
    
    # Test 3: IP address should not be empty
    assert len(ip) > 0, "IP address is empty"
    
    # Test 4: Basic IP format validation
    if '.' in ip:  # IPv4
        parts = ip.split('.')
        assert len(parts) == 4, f"Invalid IPv4 format: {ip}"
        for part in parts:
            num = int(part)
            assert 0 <= num <= 255, f"Invalid IPv4 octet in {ip}"
    elif ':' in ip:  # IPv6
        assert len(ip) <= 45, f"Invalid IPv6 length: {ip}"
        assert ip.count('::') <= 1, f"Invalid IPv6 format: {ip}"
    
    print("All tests passed!")
    print(f"IP Address: {ip}")

if __name__ == '__main__':
    run_tests()