#!/usr/bin/env python3
"""
A simple CLI calculator that performs basic arithmetic operations
and handles errors gracefully.
"""

import sys
from typing import Union


def calculate(expression: str) -> Union[float, None]:
    """
    Evaluate a simple arithmetic expression and return the result.
    Returns None if there's an error.
    """
    try:
        # Simple validation - ensure expression contains only basic operations
        # Parse the expression
        parts = expression.strip().split()
        if len(parts) != 3:
            print(f"Error: Invalid expression format '{expression}'. Use format: 'number operator number'")
            return None
            
        num1, operator, num2 = parts
        
        try:
            a = float(num1)
            b = float(num2)
        except ValueError:
            print(f"Error: '{num1}' or '{num2}' is not a valid number")
            return None
        
        # Perform calculation
        if operator == '+':
            result = a + b
        elif operator == '-':
            result = a - b
        elif operator == '*':
            result = a * b
        elif operator == '/':
            if b == 0:
                print(f"Error: Cannot divide {a} by zero - that's a mathematical mystery!")
                return None
            result = a / b
        else:
            print(f"Error: '{operator}' is not a supported operation. Use +, -, *, or /")
            return None
        
        return result
        
    except Exception as e:
        print(f"Error: Something went wrong while calculating '{expression}': {e}")
        return None


def main():
    """Main CLI interface"""
    print("🧮 Welcome to the Simple CLI Calculator! 🧮")
    print("Available operations: +, -, *, /")
    print("-" * 40)
    
    # Test the specific expressions from the user's request
    test_expressions = ["12 + 8", "10 / 0"]
    
    for expr in test_expressions:
        print(f"\nCalculating: {expr}")
        result = calculate(expr)
        if result is not None:
            print(f"Result: {result}")
    
    print("\n" + "-" * 40)
    print("Calculator finished. Goodbye! 👋")


if __name__ == "__main__":
    main()