import datetime
import time

def get_now_time():
    """
    Get the current time as a datetime object.
    
    Returns:
        datetime.datetime: Current local date and time.
        
    Raises:
        OSError: If the system time cannot be retrieved.
    """
    try:
        return datetime.datetime.now()
    except (OSError, ValueError) as e:
        raise OSError(f"Failed to get system time: {e}")

def get_now_timestamp():
    """
    Get the current time as a Unix timestamp.
    
    Returns:
        float: Current time as seconds since the Unix epoch.
        
    Raises:
        OSError: If the system time cannot be retrieved.
    """
    try:
        return time.time()
    except (OSError, ValueError) as e:
        raise OSError(f"Failed to get system time: {e}")

def get_now_formatted(format_string="%Y-%m-%d %H:%M:%S"):
    """
    Get the current time formatted as a string.
    
    Args:
        format_string (str): Format string for strftime.
        
    Returns:
        str: Formatted current time string.
        
    Raises:
        OSError: If the system time cannot be retrieved.
        ValueError: If the format string is invalid.
    """
    try:
        now = get_now_time()
        return now.strftime(format_string)
    except (OSError, ValueError) as e:
        if "Failed to get system time" in str(e):
            raise OSError(f"Failed to get system time: {e}")
        raise ValueError(f"Invalid format string: {e}")

def run_tests():
    """Run assertion tests for the time functions."""
    
    # Test get_now_time returns datetime object
    now_dt = get_now_time()
    assert isinstance(now_dt, datetime.datetime), "get_now_time should return datetime object"
    
    # Test get_now_timestamp returns float
    timestamp = get_now_timestamp()
    assert isinstance(timestamp, float), "get_now_timestamp should return float"
    assert timestamp > 0, "Timestamp should be positive"
    
    # Test get_now_formatted with default format
    formatted = get_now_formatted()
    assert isinstance(formatted, str), "get_now_formatted should return string"
    assert len(formatted) == 19, "Default format should be 19 characters"
    
    # Test get_now_formatted with custom format
    custom_formatted = get_now_formatted("%Y/%m/%d")
    assert isinstance(custom_formatted, str), "Custom format should return string"
    assert len(custom_formatted.split('/')) == 3, "Date should have three parts"
    
    # Test that formatted time can be parsed back
    parsed_time = datetime.datetime.strptime(formatted, "%Y-%m-%d %H:%M:%S")
    assert isinstance(parsed_time, datetime.datetime), "Should be able to parse formatted time"
    
    # Test time proximity (within 2 seconds)
    current_timestamp = time.time()
    retrieved_timestamp = get_now_timestamp()
    time_diff = abs(current_timestamp - retrieved_timestamp)
    assert time_diff < 2.0, f"Time difference should be minimal, got {time_diff}"
    
    print("All tests passed!")

if __name__ == '__main__':
    run_tests()