import pandas as pd
import os
import uuid
import logging
from flask import Flask, request, send_file, jsonify
import tempfile
import json
from werkzeug.utils import secure_filename
from zipfile import BadZipFile

app = Flask(__name__)
REQUIRED_COLUMNS = {"id", "reference", "amount"}

# Set up logging
logging.basicConfig(
    filename="reconciliation.log",  # Log file
    level=logging.DEBUG,  # Log level: DEBUG for detailed logs
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log format with timestamps
)

# Supported file extensions and corresponding engines
FILE_ENGINES = {
    ".xls": "openpyxl", 
    ".xlsx": "openpyxl",
    ".xlsm": "openpyxl",  
}

# Endpoint to reconcile transactions
@app.route("/reconcile", methods=["POST"])
def reconcile():
    logging.info("Received request to reconcile transactions.")
    logging.info(f"Request method: {request.method}") # Log request method for debugging
    logging.info(f"Request headers: {request.headers}") # Log request headers for debugging
    logging.info(f"Request content type: {request.content_type}") # Log request content type for debugging
    logging.info(f"Request content length: {request.content_length}") # Log request content length for debugging
    logging.info(f"Request: {request}") # Log request object for debugging
    logging.info(f"Request data: {request.form.to_dict()}") # Log request data for debugging
    logging.info(f"Request files: {request.files.to_dict()}") # Log request files for debugging
    
    # Receive file
    file = request.files.get("file")
    db_data = request.form.get("db_data")  # Getting JSON data sent as a string
    
    if not file:
        logging.error("No file uploaded.")
        return jsonify({"error": "No file uploaded"}), 400

    if not db_data:
        logging.error("No db_data provided.")
        return jsonify({"error": "Missing db_data. Expected JSON format."}), 400

    try:
        db_data = json.loads(db_data)  # Parse JSON string into a Python object
        
        if not all(col in db_data[0] for col in REQUIRED_COLUMNS):
            logging.error("Invalid DB data format. Expected columns: id, reference, amount.")
            return jsonify({"error": "Invalid DB data format. Expected columns: id, reference, amount"}), 400
    except json.JSONDecodeError:
        logging.error("Failed to decode db_data JSON.")
        return jsonify({"error": "Invalid JSON format for db_data"}), 400

    try:
        logging.info("Starting reconciliation process.")
        
        # Generate unique filenames per request using tempfile to avoid cluttering the filesystem
        file_id = str(uuid.uuid4())
        
        # Temporary directory for uploaded files and results
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, f"uploaded_transactions_{file_id}{secure_filename(file.filename)}")
            output_file = os.path.join(tmpdir, f"reconciliation_report2_{file_id}.xlsx")
            
            # Save the uploaded file to the temporary directory
            file.save(file_path)
            logging.info(f"File uploaded and saved as {file_path}.")
            
            # Get the file extension
            file_extension = os.path.splitext(file_path)[1].lower()
            
            # Ensure that the file extension is valid
            if file_extension not in FILE_ENGINES:
                logging.error(f"Unsupported file format: {file_extension}")
                return jsonify({"error": f"Unsupported file format: {file_extension}"}), 400
            
            engine = FILE_ENGINES[file_extension]
            
            # Try to read the Excel file, handle invalid file content
            try:
                with open(file_path, 'rb') as xls:
                    df_excel = pd.read_excel(xls, engine=engine)  # No chunksize here
                    logging.info("Excel file loaded into a DataFrame.")
            except BadZipFile:
                logging.error("The file is not a valid Excel file or is corrupted.")
                return jsonify({"error": "The file is not a valid Excel file or is corrupted."}), 400
            except Exception as e:
                logging.error(f"An error occurred while reading the Excel file: {str(e)}", exc_info=True)
                return jsonify({"error": f"An error occurred while reading the Excel file: {str(e)}"}), 400

            # Validate required columns in Excel
            if not REQUIRED_COLUMNS.issubset(df_excel.columns):
                logging.error("Invalid Excel format. Expected columns: id, reference, amount.")
                return jsonify({"error": "Invalid Excel format. Expected columns: id, reference, amount"}), 400

            # Keep only required columns
            df_excel = df_excel[list(REQUIRED_COLUMNS)]
            logging.info("Filtered Excel data to include only required columns.")

            # Load DB data into a DataFrame
            df_db = pd.DataFrame(db_data)  # Convert JSON to DataFrame
            logging.info("Loaded DB data into a DataFrame.")

            # Perform reconciliation
            merged = df_excel.merge(df_db, on=["id", "reference"], suffixes=("_excel", "_db"), how="outer", indicator=True)
            logging.info("Merged Excel and DB data.")

            # Identify mismatches in amount
            mismatches = merged[(merged['_merge'] == 'both') & (merged['amount_excel'] != merged['amount_db'])]
            mismatches['Mismatch Reason'] = 'Amount Mismatch'
            logging.info(f"Identified {len(mismatches)} mismatches based on amount.")

            # Separate unmatched transactions
            only_in_excel = merged[merged['_merge'] == 'left_only'].copy()
            only_in_excel['Mismatch Reason'] = 'Only in Excel'
            only_in_db = merged[merged['_merge'] == 'right_only'].copy()
            only_in_db['Mismatch Reason'] = 'Only in DB'
            logging.info(f"Separated unmatched records: {len(only_in_excel)} in Excel, {len(only_in_db)} in DB.")

            # Concatenate results
            result = pd.concat([mismatches, only_in_excel, only_in_db], ignore_index=True)
            result.drop(columns=['_merge'], inplace=True)
            logging.info(f"Concatenated results into final reconciliation DataFrame.")

            # Separate reconciled and unreconciled records
            reconciled = merged[(merged['_merge'] == 'both') & (merged['amount_excel'] == merged['amount_db'])]
            unreconciled = result

            reconciled_data = reconciled.to_dict(orient='records')
            unreconciled_data = unreconciled.to_dict(orient='records')

            # Log the info about reconciliation data (for debugging purposes)
            logging.info(f"Reconciled data: {reconciled_data}")
            logging.info(f"Unreconciled data: {unreconciled_data}")

            # Return both reconciled and unreconciled data as JSON response
            logging.info("Sending reconciliation data as JSON response.")
            return jsonify({
                "reconciled": reconciled_data,
                "unreconciled": unreconciled_data
            })

    except Exception as e:
        logging.error(f"An error occurred during reconciliation: {str(e)}", exc_info=True)
        return jsonify({"error": f"An error occurred during reconciliation: {str(e)}"}), 500

if __name__ == "__main__":
    logging.info("Starting Flask app.")
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
