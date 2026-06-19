import numpy as np
import matplotlib.pyplot as plt

def fit_line_to_points(x_points, y_points):
    """
    Fits a straight line to a set of 2D points.
    """
    # 1. Use NumPy's polyfit to find the slope (m) and y-intercept (b)
    # The '1' indicates we want a first-degree polynomial (a straight line)
    slope, intercept = np.polyfit(x_points, y_points, 1)
    
    print(f"Line of best fit: y = {slope:.4f}x + {intercept:.4f}")
    
    # 2. Generate the y values for the fitted line based on our x points
    # Equation of a line: y = mx + b
    line_y_values = (slope * x_points) + intercept
    
    # 3. Visualize the results
    plt.figure(figsize=(8, 5))
    
    # Scatter plot for the original data points
    plt.scatter(x_points, y_points, color='blue', label='Original Points')
    
    # Line plot for the fitted line
    plt.plot(x_points, line_y_values, color='red', label='Line of Best Fit')
    
    # Formatting the chart
    plt.title('Linear Regression / Line of Best Fit')
    plt.xlabel('X values')
    plt.ylabel('Y values')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    
    # Show the plot
    plt.show()

if __name__ == "__main__":
    # --- Example Usage ---
    
    # Sample input points (you can replace these with your own data)
    # x and y arrays must be the same length
    x_data = np.array([-25.0, -24.0, -20.0, -17.0, -15.0])
    
    # Adding some random noise so the points don't form a perfectly straight line
    y_data = np.array([1.0734, 1.049, 0.959, 0.886, 0.824])
    
    fit_line_to_points(x_data, y_data)