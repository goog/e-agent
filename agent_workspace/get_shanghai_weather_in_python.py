import json
import urllib.request
import urllib.error
from typing import Dict, Optional, Any


def get_shanghai_weather(api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Get current weather data for Shanghai.
    
    Args:
        api_key: Optional API key for OpenWeatherMap. If not provided,
                uses a free endpoint with limited data.
    
    Returns:
        Dictionary containing weather data.
    
    Raises:
        urllib.error.URLError: If there's a network error.
        ValueError: If the API response is invalid.
    """
    try:
        if api_key:
            # Using OpenWeatherMap API with API key
            url = f"http://api.openweathermap.org/data/2.5/weather?q=Shanghai,CN&appid={api_key}&units=metric"
        else:
            # Using free public API (wttr.in) as fallback
            url = "https://wttr.in/Shanghai?format=j1"
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read().decode('utf-8')
            weather_data = json.loads(data)
            
            if api_key:
                # Parse OpenWeatherMap response
                result = {
                    'city': weather_data.get('name', 'Shanghai'),
                    'temperature': weather_data.get('main', {}).get('temp'),
                    'feels_like': weather_data.get('main', {}).get('feels_like'),
                    'humidity': weather_data.get('main', {}).get('humidity'),
                    'description': weather_data.get('weather', [{}])[0].get('description'),
                    'wind_speed': weather_data.get('wind', {}).get('speed'),
                    'source': 'OpenWeatherMap'
                }
            else:
                # Parse wttr.in response
                current_condition = weather_data.get('current_condition', [{}])[0]
                result = {
                    'city': 'Shanghai',
                    'temperature': float(current_condition.get('temp_C', 0)),
                    'feels_like': float(current_condition.get('FeelsLikeC', 0)),
                    'humidity': float(current_condition.get('humidity', 0)),
                    'description': current_condition.get('weatherDesc', [{}])[0].get('value'),
                    'wind_speed': float(current_condition.get('windspeedKmph', 0)) / 3.6,
                    'source': 'wttr.in'
                }
            
            # Validate we have at least some data
            if result['temperature'] is None:
                raise ValueError("Invalid weather data received")
            
            return result
            
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse weather data: {e}")
    except urllib.error.URLError as e:
        raise urllib.error.URLError(f"Network error while fetching weather: {e}")


def run_tests() -> None:
    """Run assertion tests for the weather function."""
    
    # Test 1: Test that function returns a dictionary with expected keys
    # We'll mock the response for testing since we can't rely on actual API calls
    import unittest.mock as mock
    
    # Create mock response for wttr.in
    mock_response = {
        'current_condition': [{
            'temp_C': '25',
            'FeelsLikeC': '27',
            'humidity': '65',
            'weatherDesc': [{'value': 'Partly cloudy'}],
            'windspeedKmph': '18'
        }]
    }
    
    with mock.patch('urllib.request.urlopen') as mock_urlopen:
        mock_read = mock.Mock()
        mock_read.read.return_value = json.dumps(mock_response).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_read
        
        result = get_shanghai_weather()
        
        # Basic structure tests
        assert isinstance(result, dict), "Result should be a dictionary"
        assert 'temperature' in result, "Result should contain temperature"
        assert 'description' in result, "Result should contain description"
        assert 'humidity' in result, "Result should contain humidity"
        assert result['city'] == 'Shanghai', "City should be Shanghai"
        assert result['source'] == 'wttr.in', "Source should be wttr.in"
        
        # Type tests
        assert isinstance(result['temperature'], float), "Temperature should be float"
        assert isinstance(result['feels_like'], float), "Feels like should be float"
        assert isinstance(result['humidity'], float), "Humidity should be float"
        assert isinstance(result['wind_speed'], float), "Wind speed should be float"
        
        # Value tests for our mock data
        assert result['temperature'] == 25.0, f"Expected 25.0, got {result['temperature']}"
        assert result['feels_like'] == 27.0, f"Expected 27.0, got {result['feels_like']}"
        assert result['humidity'] == 65.0, f"Expected 65.0, got {result['humidity']}"
        assert result['description'] == 'Partly cloudy', f"Expected 'Partly cloudy', got {result['description']}"
    
    # Test 2: Test error handling for invalid JSON
    with mock.patch('urllib.request.urlopen') as mock_urlopen:
        mock_read = mock.Mock()
        mock_read.read.return_value = b'invalid json'
        mock_urlopen.return_value.__enter__.return_value = mock_read
        
        try:
            get_shanghai_weather()
            assert False, "Should have raised ValueError for invalid JSON"
        except ValueError:
            pass  # Expected
    
    # Test 3: Test error handling for network issues
    with mock.patch('urllib.request.urlopen') as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.URLError('Network error')
        
        try:
            get_shanghai_weather()
            assert False, "Should have raised URLError for network issues"
        except urllib.error.URLError:
            pass  # Expected
    
    print("All tests passed!")


if __name__ == '__main__':
    run_tests()