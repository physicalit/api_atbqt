import subprocess
from flask import Flask, render_template, jsonify  # Import jsonify

import pandas as pd

app = Flask(__name__)

# Sample data (replace with your own data source)

df = pd.read_excel('../results/4saleit.xlsx')

@app.route('/')
def index():
    data_for_table = df.to_dict('records')
    return render_template('index.html', table_data=data_for_table)

@app.route('/run_scraper')
def run_scraper():
    try:
        result = subprocess.run(['python', 'scrap_4sale.py'], capture_output=True, text=True)
        print(result.stdout)  # Print the output if needed
        return jsonify({'success': True}) 
    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({'success': False}) 

if __name__ == '__main__':
    app.run(debug=True)