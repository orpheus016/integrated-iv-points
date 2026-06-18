import re
import csv
import sys

def convert_text_to_csv(input_text, output_filepath):
    # Regex designed to extract floating-point values from structural 'Voltage' and 'Current' lines
    # It explicitly ignores metadata lines starting with 'Sending R='
    pattern = re.compile(r"Voltage:\s+([\d.]+)\s+V\s+\|\s+Current:\s+([\d.]+)\s+mA")
    
    with open(output_filepath, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(["voltage", "current_mA"])
        
        for line in input_text.strip().splitlines():
            match = pattern.search(line)
            if match:
                voltage = match.group(1)
                # Converting to float and back to string ensures formatting matches '4.0' instead of '4.000'
                current_mA = str(float(match.group(2)))
                writer.writerow([voltage, current_mA])

# Example raw string payload
text_data = """[YOUR_TEXT_GOES_HERE]"""

# Execution
convert_text_to_csv(text_data, "output.csv")