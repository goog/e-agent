import calendar
import datetime

def generate_markdown_calendar(year, month):
    """
    Generate a markdown calendar for a specific month and year.
    
    Args:
        year (int): Year for the calendar
        month (int): Month for the calendar (1-12)
    
    Returns:
        str: Markdown formatted calendar
    """
    if not isinstance(year, int) or not isinstance(month, int):
        raise TypeError("Year and month must be integers")
    
    if year < 1 or year > 9999:
        raise ValueError("Year must be between 1 and 9999")
    
    if month < 1 or month > 12:
        raise ValueError("Month must be between 1 and 12")
    
    # Create calendar instance
    cal = calendar.Calendar(firstweekday=0)  # 0 = Monday, 6 = Sunday
    
    # Get month days as a list of weeks
    month_days = cal.monthdayscalendar(year, month)
    
    # Month header with month name and year
    month_name = calendar.month_name[month]
    markdown = f"# {month_name} {year}\n\n"
    
    # Day headers (Monday to Sunday)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    markdown += "| " + " | ".join(day_names) + " |\n"
    markdown += "|" + " --- |" * 7 + "\n"
    
    # Add each week
    for week in month_days:
        week_str = []
        for day in week:
            if day == 0:
                week_str.append(" ")
            else:
                # Check if it's today
                today = datetime.date.today()
                if year == today.year and month == today.month and day == today.day:
                    week_str.append(f"**{day}**")
                else:
                    week_str.append(str(day))
        
        markdown += "| " + " | ".join(week_str) + " |\n"
    
    return markdown

def generate_monthly_calendars(start_year, start_month, months_count=12):
    """
    Generate multiple monthly calendars.
    
    Args:
        start_year (int): Starting year
        start_month (int): Starting month (1-12)
        months_count (int): Number of months to generate
    
    Returns:
        str: Combined markdown calendars
    """
    if months_count < 1:
        raise ValueError("months_count must be at least 1")
    
    markdown = ""
    
    for i in range(months_count):
        # Calculate current month and year
        total_months = start_month + i - 1
        current_year = start_year + total_months // 12
        current_month = (total_months % 12) + 1
        
        markdown += generate_markdown_calendar(current_year, current_month)
        markdown += "\n---\n\n"
    
    return markdown

def save_calendar_to_file(content, filename="calendar.md"):
    """
    Save calendar content to a markdown file.
    
    Args:
        content (str): Calendar content
        filename (str): Output filename
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error saving file: {e}")
        return False

def run_tests():
    """Run tests for the calendar functions."""
    
    # Test 1: Basic calendar generation
    test_cal = generate_markdown_calendar(2024, 1)
    assert "# January 2024" in test_cal
    assert "| Mon | Tue | Wed | Thu | Fri | Sat | Sun |" in test_cal
    assert "| 1 | 2 | 3 | 4 | 5 | 6 | 7 |" in test_cal or "|  1 |  2 |" in test_cal
    
    # Test 2: Invalid month
    try:
        generate_markdown_calendar(2024, 13)
        assert False, "Should have raised ValueError for invalid month"
    except ValueError as e:
        assert "Month must be between 1 and 12" in str(e)
    
    # Test 3: Invalid year
    try:
        generate_markdown_calendar(0, 1)
        assert False, "Should have raised ValueError for invalid year"
    except ValueError as e:
        assert "Year must be between 1 and 9999" in str(e)
    
    # Test 4: Invalid type
    try:
        generate_markdown_calendar("2024", 1)
        assert False, "Should have raised TypeError for string year"
    except TypeError as e:
        assert "Year and month must be integers" in str(e)
    
    # Test 5: Multiple months
    multi_cal = generate_monthly_calendars(2024, 1, 3)
    assert "# January 2024" in multi_cal
    assert "# February 2024" in multi_cal
    assert "# March 2024" in multi_cal
    
    # Test 6: Year rollover
    rollover_cal = generate_monthly_calendars(2024, 12, 3)
    assert "# December 2024" in rollover_cal
    assert "# January 2025" in rollover_cal
    assert "# February 2025" in rollover_cal
    
    # Test 7: Save to file
    success = save_calendar_to_file(test_cal, "test_calendar.md")
    assert success == True
    
    # Test 8: Check month boundaries
    feb_cal = generate_markdown_calendar(2024, 2)
    assert "# February 2024" in feb_cal
    # 2024 is a leap year, so February should have 29 days
    assert "29" in feb_cal
    
    print("All tests passed!")

if __name__ == '__main__':
    run_tests()