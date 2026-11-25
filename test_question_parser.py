from backend.app.document_processing.question_parser import parse_questions

sample_text = """
SQL Questions

1. Maximum Salary (5 marks): Write a query to display the employee name and salary of the employee(s) who receive the highest salary in the company. Your query must handle ties.

2. Department-wise Average Salary (5 marks): Write a query to display each department name and its average employee salary. Show only departments whose average salary is greater than 60,000.

3. Employees Above Department Average (5 marks): Write a query to display the names and salaries of employees whose salary is greater than the average salary of their own department.

4. Second-Highest Salary (5 marks): Write a query to find the second-highest distinct salary in the EMPLOYEE table.

5. Department with Maximum Employees (5 marks): Write a query to display the department name and number of employees for the department that has the highest number of employees. Handle ties if more than one department has the same count.

6. Employee and Manager Details (5 marks): Write a query to display each employee's name along with their manager's name. Include employees who do not have a manager, showing NULL for the manager name.
"""

questions = parse_questions(sample_text)

print("Total questions:", len(questions))

for question in questions:
    print("\n", question)