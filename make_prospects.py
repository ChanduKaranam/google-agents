"""Build prospects.xlsx — the 15-row showcase dataset.

Ten visible columns plus a hidden Phone column (the Tilicho platform reads
numbers from it; it never appears on screen). Run: python make_prospects.py
"""

from openpyxl import Workbook

HEADER = ['Name', 'Age', 'Residency', 'Marital Status', 'Dependents',
          'Occupation', 'Income (S$K)', 'Tobacco', 'Cover (S$K)',
          'Life Event', 'Phone']

ROWS = [
    ('Amir Hassan', 34, 'Citizen', 'Married', 2, 'IT Engineer', 120, 'N', 100, 'New child'),
    ('Tan Wei Ming', 29, 'Citizen', 'Married', 0, 'Software Developer', 95, 'N', 0, 'Marriage'),
    ('Siti Zulaikha', 35, 'Citizen', 'Married', 2, 'Teacher', 72, 'N', 150, 'New child'),
    ('Ahmad Faizal', 41, 'PR', 'Married', 3, 'Site Supervisor', 78, 'Y', 50, 'Home loan'),
    ('Nurul Aisyah', 31, 'PR', 'Married', 1, 'Marketing Manager', 85, 'N', 200, 'Home loan'),
    ('Rajesh Kumar', 45, 'Citizen', 'Married', 3, 'Logistics Manager', 110, 'Y', 300, '—'),
    ('Wong Kai Jie', 52, 'Citizen', 'Married', 1, 'Business Owner', 250, 'N', 1500, '—'),
    ('Muhammad Irfan', 30, 'Citizen', 'Married', 1, 'Delivery Driver', 48, 'Y', 0, 'New child'),
    ('Chen Xiu Ying', 44, 'PR', 'Divorced', 2, 'HR Manager', 98, 'N', 400, '—'),
    ('Ganesh Pillai', 36, 'Citizen', 'Married', 2, 'Sales Manager', 90, 'N', 250, 'Home loan'),
    ('Ong Boon Keat', 49, 'Citizen', 'Married', 2, 'Engineer', 130, 'Y', 600, '—'),
    ('Priya Nair', 27, 'Citizen', 'Single', 0, 'Nurse', 65, 'N', 100, 'Job change'),
    ('Lim Mei Ling', 38, 'Citizen', 'Married', 2, 'Accountant', 105, 'N', 800, '—'),
    ('David Chua', 58, 'Citizen', 'Married', 0, 'Consultant', 180, 'N', 1200, '—'),
    ('Nur Farhana', 26, 'Citizen', 'Single', 0, 'Graphic Designer', 55, 'N', 0, '—'),
]

if __name__ == '__main__':
    wb = Workbook()
    ws = wb.active
    ws.title = 'Prospects'
    ws.append(HEADER)
    for i, row in enumerate(ROWS, start=1):
        ws.append(list(row) + [f'+65 8{i:03d} {i:04d}'])
    ws.column_dimensions['K'].hidden = True  # Tilicho-only
    wb.save('prospects.xlsx')
    print(f'prospects.xlsx written: {len(ROWS)} rows')
