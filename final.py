import sqlite3  
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import itertools
from matplotlib.ticker import MaxNLocator
from reportlab.pdfgen import canvas
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

def create_database():
    conn = sqlite3.connect('cricket_data.db')
    conn.close()

def record_runs_from_csv(match_no, csv_filename):
    df = pd.read_csv(csv_filename)
    df['match_no'] = match_no

    conn = sqlite3.connect('cricket_data.db')
    df.to_sql('cricket_data', conn, index=False, if_exists='replace')
    conn.close()

def create_manhattan_plot(df, match_no, inning_choice):
    if inning_choice not in [1, 2]:
        print("Invalid inning number. Please enter 1 or 2.")
        return

    subset = df[(df['match_no'] == match_no) & (df['inningno'] == inning_choice)].copy()

    # Convert the 'over' column to integers
    subset['over'] = subset['over'].apply(lambda x: int(x))

    fig, ax1 = plt.subplots(figsize=(12, 8))

    overs = range(1, 21)  # List of overs from 1 to 20

    # Aggregate runs and wickets per over
    grouped_runs = subset.groupby(['over'])['score'].sum().reindex(overs, fill_value=0)
    grouped_wickets = subset[subset['outcome'] == 1].groupby(['over']).size().reindex(overs, fill_value=0)

    # Bar plot for runs
    ax1.bar(overs, grouped_runs, width=0.4, align='center', color='blue', alpha=0.7, label=f'Inning {inning_choice}')

    # Scatter plot for wickets
    wicket_overs = subset[subset['outcome'] == 'w']['over']
    ax1.scatter(wicket_overs, [0] * len(wicket_overs), color='red', s=200, marker='o', label='Wickets', zorder=10)  # Set higher zorder to appear above bars


    ax1.set_xlabel('Overs')
    ax1.set_ylabel('Runs')
    ax1.set_xlim(0.5, 20.5)  # Adjust x-axis limits to align bars with ticks
    ax1.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax1.legend()

    plt.title(f'Manhattan Plot - Match {match_no}, Inning {inning_choice}')
    plt.show()

def create_worm_chart(df, match_no, inning_choice):
    # Filter data for the selected match and inning
    subset = df[(df['match_no'] == match_no) & (df['inningno'] == inning_choice)]
    
    # Group data by over and calculate total runs at each over
    grouped_runs = subset.groupby('over')['score'].sum().cumsum()

    # Plot the worm graph
    plt.figure(figsize=(10, 6))
    plt.plot(grouped_runs.index, grouped_runs.values, label='Team Runs', marker='o')

    # Customize the appearance of the graph
    plt.title(f'Team Runs - Match {match_no}, Inning {inning_choice}')
    plt.xlabel('Overs')
    plt.ylabel('Total Runs')
    plt.legend()
    plt.grid(True)
    plt.show()

def calculate_run_rate(df):
    df['runs_cumulative'] = df.groupby(['inningno'])['score'].cumsum()
    df['balls_cumulative'] = df.groupby(['inningno']).cumcount() + 1
    df['run_rate'] = (df['runs_cumulative'] / df['balls_cumulative']) * 6
    return df

def create_run_rate_plot(df, match_no, inningno):
    subset = df[(df['match_no'] == match_no) & (df['inningno'] == inningno)].copy()

    # Ensure that the DataFrame is sorted by over and ballnumber
    subset = subset.sort_values(by=['over', 'ballnumber'])

    # Calculate cumulative runs and overs
    subset['cumulative_runs'] = subset.groupby('over')['score'].cumsum()
    subset['cumulative_overs'] = subset.groupby('over').cumcount() + 1

    # Calculate run rate
    subset['run_rate'] = subset['cumulative_runs'] / (subset['cumulative_overs'] / 6)

    # Plotting with a smoother run rate curve
    window_size = 5  # You can adjust the window size as needed
    weights = np.ones(window_size) / window_size
    subset['smoothed_run_rate'] = subset['run_rate'].rolling(window=window_size, min_periods=1, center=True).mean()

    # Plotting
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(subset['over'], subset['smoothed_run_rate'], color='orange', marker='o')

    ax.set_xlabel('Overs')
    ax.set_ylabel('Run Rate')
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    plt.title(f'Run Rate Plot - Match {match_no}, Inning {inningno}')
    plt.show()

def create_match_summary_pdf(match_no):
    conn = sqlite3.connect('cricket_data.db')
    cursor = conn.cursor()

    doc = SimpleDocTemplate(f"match_{match_no}_summary.pdf", pagesize=letter)
    elements = []

    for inning in [1, 2]:
        # Calculate total score and total wickets for the specific match and inning
        cursor.execute("""
            SELECT 
                SUM(score) AS total_score, 
                COUNT(CASE WHEN outcome = 'w' THEN 1 END) AS total_wickets 
            FROM cricket_data 
            WHERE match_no=? AND inningno=?
        """, (match_no, inning))
        
        # Fetch the results and assign them to variables
        total_score, total_wickets = cursor.fetchone()

        # Create a list to store each row of the table
        data = [['Batsman', 'Runs', 'Balls Faced', '4s', '6s', 'Strike Rate']]

        # Calculate batsman statistics for the specific match and inning
        cursor.execute("""
            SELECT 
                batter,
                SUM(score) AS runs,
                COUNT(*) AS balls_faced,
                SUM(CASE WHEN score = 4 THEN 1 ELSE 0 END) AS fours,
                SUM(CASE WHEN score = 6 THEN 1 ELSE 0 END) AS sixes
            FROM cricket_data 
            WHERE match_no=? AND inningno=? AND outcome != 'w'
            GROUP BY batter
        """, (match_no, inning))
        batsman_stats = cursor.fetchall()

        # Calculate strike rate for each batsman
        for batsman, runs, balls_faced, fours, sixes in batsman_stats:
            strike_rate = (runs / balls_faced) * 100 if balls_faced else 0
            data.append([batsman, runs, balls_faced, fours, sixes, f'{strike_rate:.2f}'])

        # # Add total score and total wickets to the top of the table
        # data.insert(0, [f'Total Score: {total_score}', f'Total Wickets: {total_wickets}', '', '', '', ''])

        # Create a Table object and add it to the elements to be added to the PDF
        table = Table(data)
        elements.append(table)

    # Generate the PDF
    doc.build(elements)

    conn.close()


def main():
    create_database()

    print('_________________________________________________________________________________')
    print('Welcome to Cricket Score Dashboard')
    print('_________________________________________________________________________________')
    print('This dashboard has data of the recently concluded IPL 2023. \nJust enter the match number, and see the various analaytics for that match!')
    print('_________________________________________________________________________________')
    print('\n')
    match_no=int(input("Enter match no: "))
    csv_filename = 'ipl.csv'
    record_runs_from_csv(match_no, csv_filename)

    df = pd.read_csv(csv_filename)  # Read CSV file here

    while True:
        print("\nSelect Operation:")
        print("1. Display Manhattan Chart")
        print("2. Display Worm Chart")
        print("3. Display Run Rate Chart")
        print("4. Generate PDF Summary")
        print("5. Exit")

        try:
            operation = int(input("Enter your choice: "))
        except ValueError:
            print("Invalid input. Please enter a number.")
            continue

        if operation in [1, 2, 3]:
            inning_choice = int(input("Enter inning number (1 or 2): "))
            if inning_choice not in [1, 2]:
                print("Invalid inning number. Please enter 1 or 2.")
                continue

        if operation == 1:
            create_manhattan_plot(df, match_no, inning_choice)

        if operation == 2:
            create_worm_chart(df,match_no,inning_choice)
        
        if operation == 3:
            create_run_rate_plot(df, match_no, inning_choice)

        if operation == 4:
            create_match_summary_pdf(match_no)

        if operation ==5:
            print("\nExiting...")
            print("Thank You")
            return;
        
        #To print all the values in the table. For verification Purposes only
        if operation==6:
            conn = sqlite3.connect('cricket_data.db')
            cursor = conn.cursor()

            # Fetch all records from the cricket_data table for match match_no
            cursor.execute("SELECT * FROM cricket_data WHERE match_no=?", (match_no,))
            records = cursor.fetchall()

            # Print the column names
            column_names = [description[0] for description in cursor.description]
            print("\t".join(column_names))

            # Print each record
            for record in records:
                print("\t".join(map(str, record)))

            conn.close()
if __name__ == "__main__":
    main()