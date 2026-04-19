def quick_sort(arr):
    """Sort a list using the quicksort algorithm."""
    if not isinstance(arr, list):
        raise TypeError("Input must be a list")
    
    if len(arr) <= 1:
        return arr
    
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    
    return quick_sort(left) + middle + quick_sort(right)


def run_tests():
    """Test the quick_sort function with various inputs."""
    # Test empty list
    assert quick_sort([]) == []
    
    # Test single element
    assert quick_sort([5]) == [5]
    
    # Test already sorted list
    assert quick_sort([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]
    
    # Test reverse sorted list
    assert quick_sort([5, 4, 3, 2, 1]) == [1, 2, 3, 4, 5]
    
    # Test unsorted list
    assert quick_sort([3, 6, 8, 10, 1, 2, 1]) == [1, 1, 2, 3, 6, 8, 10]
    
    # Test list with duplicates
    assert quick_sort([5, 2, 8, 2, 5, 1]) == [1, 2, 2, 5, 5, 8]
    
    # Test list with negative numbers
    assert quick_sort([-3, 0, 5, -8, 2]) == [-8, -3, 0, 2, 5]
    
    # Test list with strings
    assert quick_sort(["banana", "apple", "cherry"]) == ["apple", "banana", "cherry"]
    
    # Test type error
    try:
        quick_sort("not a list")
        assert False, "Should have raised TypeError"
    except TypeError:
        pass
    
    # Test type error with mixed types (should raise TypeError during comparison)
    try:
        quick_sort([1, "two", 3])
        assert False, "Should have raised TypeError"
    except TypeError:
        pass
    
    print("All tests passed!")


if __name__ == '__main__':
    run_tests()