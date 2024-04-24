# database_gui.py
# Ethan York
# Dr. Wang
# University of Kentucky

# User interface that allows GM DOE datasets to quickly be converted into HDF5 files

# NECESSARY ASSUMPTIONS:
#           1) For all DOEs, the Analysis headers are identical (not all have data)
#           2) For all DOEs, the ParamCurrent headers are identical (all contain data)
#           3) No headers shoud contain the character ':'. It is used to split the name and example data from parameter list
#           4) ParamCurrent file will contain 'Bi-Msec', 'Current' and a vspotid matching the analysis file (defined below)
#           5) Analysis file will contain a column called 'Bi-Msec'

from tkinter import filedialog
import tkinter as tk
import customtkinter
from tqdm import tqdm # to display loading bar
import pandas as pd
import numpy as np
import h5py
import csv
import os
import re

import matplotlib.pyplot as plt

# Global Constants
schedule_id = 'vspotid' # Use this to set which attribute uniquely defines a welding schedule
weld_id = 'Bi-PartID' # Use this to set which attribute uniquely defines an individual weld
msec = 'Bi-Msec' # Use this to set which attribute defines time steps
detail_mode_header = 'Bi-WTC Mode'
current_header_analysis = 'current_data' # header for current data in the analysis file
current_header_schedule = 'Current' # header for current data in the paramCurrent file
DOE_header = '# for DoE Based Model' # header for the doe number
req_headers = [schedule_id,weld_id,msec,detail_mode_header,DOE_header] # headers that must be present in Analysis data for processing

# FUNCTIONS ========================================================================================================================

# Natural sorting key function
# Custom sorting key function for .sort to perform a natrual sort (e.g. "DOE-2" < "DOE-11")
def natural_sort_key(s):
    # Use regular expression to find numbers and split the input string
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

# Get active switches
# Takes in a scrollableFrame object and returns the active switches
def get_switches(parent: customtkinter.CTkScrollableFrame):
    active_switches = []
    for switch in parent.winfo_children():
        if switch.get() == 1:
            active_switches.append(switch.cget('text'))
    return(active_switches)

# Check if all arrays equal
def check_equal_arrays(input): # input is a list of 1d arrays
    if len(input) == 0:
        print("ERROR determining if headers are the same: input to 'check_equal_arrays' was empty")
        return False
    first_array = input[0]  # Consider the first array as a reference for comparison.
    shortest_length = min(map(len, input)) # get the number of elements in the shortest array
    for array in input[1:]: # for each array in input (starting at index 1)...
        for i in range(shortest_length): # iterate through all indexes of shortest array
            if array[i] != first_array[i]: # if any elements don't match...
                return False
    return True

# Find columns with no blanks (used to discard unused headers)
def find_valid_columns(input): # input should be a list of arrays. Each array being the second row of a DOE
    analysis_result = [] # initialize
    for i in range(len(input[0])): # iterate through the second row of each DOE
        if all(array[i] for array in input): # if each index, for all DOEs, has a value...
            analysis_result.append(i) # then add that index to the result array
    return(analysis_result)

# Clear Frame Function
def clear_frame(frame:customtkinter.CTkScrollableFrame):
    for widget in frame.winfo_children():
        widget.destroy()

# Identify Attributes Function
def identify_attr(dataframe):
    attributes, time_series = [], []
    # check each selected header for more than 1 unique value
    for header in dataframe.columns:
        unique_values = dataframe[header].nunique()
        if unique_values == 1:
            attributes.append(header)
        else:
            time_series.append(header)
    return attributes, time_series

# Generate schedule map function (Needs to be optimized, I've wasted too much time and am moving on)
def generate_schedule_map(analysis_df,paramCurrent_df):
    schedule_map = []
    for weld in tqdm(analysis_df.groups.keys(), desc="Generating Schedule Map"): # iterate over every weld in dataframe
        schedule_found = False # bool used to ensure all welds have a matching schedule
        weld_vspotid = analysis_df.get_group(weld)[schedule_id].iloc[0] # get the vspotid of current weld
        for schedule in paramCurrent_df.groups.keys(): # iterate over all welding schedules
            schedule_vspotid = paramCurrent_df.get_group(schedule)[schedule_id].iloc[0] # get the vspotid of current schedule
            if  weld_vspotid == schedule_vspotid:
                schedule_map.append([weld, schedule])
                schedule_found = True
                break # exit for loop
        if not schedule_found:
            print("ERROR: no schedule found with vspotid: ", weld_vspotid)
            return
    return schedule_map

# Linear Interpolation Function
def linear_interpolation(index_column, *data_columns):
    interpolated_index = []
    interpolated_data = [[] for _ in range(len(data_columns))] # initialize list of empty arrays

    # fill interpolation arrays
    for i in range(len(index_column) - 1): # iterate over each index in provided index_column (-1: skip last data point)
        interpolated_index.append(index_column[i]) # add index to new index array
        
        # fill row with data from each column in the dataset
        for j in range(len(data_columns)): 
            interpolated_data[j].append(data_columns[j][i])

        # find difference between indexes
        diff = index_column[i + 1] - index_column[i]
        if diff > 1: # only interpolate if there is a gap in the indexes
            gap_size = diff - 1 # find gap size
            for k in range(1, gap_size + 1): # iterate the index gap size
                interpolated_index.append(index_column[i] + k) # add in missing index values
                for j in range(len(data_columns)): # iterate over each data column in current row
                    interpolated_data[j].append(data_columns[j][i] + (data_columns[j][i + 1] - data_columns[j][i]) * k / diff)

    # handles the last data point
    interpolated_index.append(index_column[-1])
    for j in range(len(data_columns)): # iterate through each data column
        interpolated_data[j].append(data_columns[j][-1]) # make it match the last value of provided data

    return interpolated_index, interpolated_data

# Add zeros at missing indexes function (used to set 0 instead of interpolate for current data)
def add_zeros_at_missing_indexes(indexes, data):
    new_data = np.zeros(max(indexes))  # Create an array of zeros with the required length
    new_data[indexes - 1] = data  # Replace the zeros at the adjusted indices with the data
    return new_data

# Get Dataframes
# Function that takes in a list of headers and looks at elements of the GUI to create a 2 dataframes for all analysis and all paramcurrent CSV files
def get_dataframes(headers):
    # create list of paths to our DOEs
    analysis_filepaths, paramCurrent_filepaths = [],[]
    selected_DOEs = get_switches(DOEList) # get list of selected DOEs
    for selected_DOE in selected_DOEs: # iterate through list of selected DOEs
        print(selected_DOE)
        directory = entry_1.get() + "\\" + selected_DOE # define the directory containing data files
        for file in os.listdir(directory): # Iterate through files in the directory
            if 'Analysis' in file: # if the current file name contains 'Analysis'...
                analysis_filepaths.append(os.path.join(directory, file)) # add analysis path to list
            if 'ParamCurrent' in file: # if the current file name contains 'ParamCurrent'...
                paramCurrent_filepaths.append(os.path.join(directory, file)) # add schedule path to list

    # Create single dataframe for all Analysis data
    list_of_dataframes = []
    for filepath in analysis_filepaths:
        df = pd.read_csv(filepath,usecols=headers,low_memory=False,na_values='') # convert entire CSV at current path into a dataframe
        list_of_dataframes.append(df) # add data frame to the list
    # Concatenate the dataframes and group by welds
    analysis_df = pd.concat(list_of_dataframes, ignore_index=True)\
        .sort_values([msec, schedule_id])\
        .groupby([weld_id, DOE_header]) # concatenate all data frames into 1 (grouped into weld_ids and DOEs) (sorted by msec)
  
    # Create single dataframe for all ParamCurrent data
    list_of_dataframes = []
    for filepath in paramCurrent_filepaths:
        df = pd.read_csv(filepath,low_memory=False,na_values='') # convert entire CSV at current path into a dataframe
        list_of_dataframes.append(df) # add dataframe to list
    # Concatenate the dataframes and group by welds
    paramCurrent_df = pd.concat(list_of_dataframes, ignore_index=True)\
        .sort_values([msec, schedule_id])\
        .groupby([schedule_id, DOE_header])\
        [[msec,current_header_schedule,schedule_id]] # only take relevant columns (grouped into weld_ids and DOEs) (sorted by msec)
    
    return analysis_df, paramCurrent_df

# browse button pressed
def browse_file():
    folder_path = filedialog.askdirectory() # open folder selection dialogue
    entry_1.delete(0, tk.END) # clear the textbox
    entry_1.insert(0,folder_path) # insert file_path from file dialog

    # Fill data set box
    folders = [f.name for f in os.scandir(folder_path) if f.is_dir()] # get all folder names below selected folder
    folders.sort(key=natural_sort_key) # Sort folders using custom natural sort key
    for index, folder in enumerate(folders):
        dswitch = customtkinter.CTkSwitch(master=DOEList, text=folder)
        dswitch.grid(row=index, column=0, padx=10, pady=(0, 20),sticky="w")
        dswitch.bind("<ButtonRelease-1>", load_parameters)  # trigger function when switch is changed

# Populate parameter options
def load_parameters(event):
    # Initialize arrays that will hold the first and second rows of our data files
    analysis_first_rows, paramCurrent_first_rows, analysis_second_rows = [], [], []
    selected_DOEs = get_switches(DOEList) # get list of selected DOEs
    selected_DOEs.sort(key=natural_sort_key) # Sort using custom natural sort key

    # If no DOEs selected
    if selected_DOEs == []:
        clear_frame(param_list) # resets parameter list
        return # exit function
    
    # Get headers and first row data for all selected DOEs
    for DOE in selected_DOEs: # iterate through list of selected DOEs
        directory = entry_1.get() + "\\" + DOE # define the directory containing data files
        for file in os.listdir(directory): # Iterate through files in the directory

            # Load analysis headers
            if 'Analysis' in file: # if the current file name contains 'Analysis'...
                filepath = os.path.join(directory, file) # then this is our desired file path
                with open(filepath, newline='') as csvfile: # define analysis file as CSV
                    csv_reader = csv.reader(csvfile) # define CSV reader
                    analysis_first_rows.append(next(csv_reader)) # Read the first row
                    analysis_second_rows.append(next(csv_reader)) # Read second row
                analysis_file_found = True
                
            # Load paramcurrent headers
            if 'ParamCurrent' in file: # if the current folder name contains 'ParamCurrent'...
                filepath = os.path.join(directory, file) # then this is our desired file path
                with open(filepath, newline='') as csvfile: # define analysis file as CSV
                    csv_reader = csv.reader(csvfile) # define CSV reader
                    paramCurrent_first_rows.append(next(csv_reader)) # Read the first row
                paramCurrent_file_found = True

    # print error messages
    if not analysis_file_found:
        print("ERROR: No Analysis file found for " + DOE)
        return # exit function
    if not paramCurrent_file_found:
        print("ERROR: No ParamCurrent file found for " + DOE)
        return # exit function

    # Verify each DOE has matching headers
    if check_equal_arrays(analysis_first_rows) and check_equal_arrays(paramCurrent_first_rows):
        # Find indexes of every column where all selected DOEs have data
        analysis_indexes = find_valid_columns(analysis_second_rows)
    else:
        print("ERROR: Headers aren't consistent")
        return # exit function
    
    # Generate Parameter switches
    parameters_text = [f"{column}  :  [ {analysis_second_rows[0][i]} ]" for i,column in enumerate(analysis_first_rows[0])] # prepare switch text (.rstrip() removes end spaces)
    clear_frame(param_list) # resets parameter list
    for index,value in enumerate(analysis_indexes):
        pswitch = customtkinter.CTkSwitch(master=param_list, text=parameters_text[value])
        pswitch.grid(row=index, column=0, padx=10, pady=(0, 20),sticky="w")

# Submit button pressed
def submit_button():
    # Create array of selected headers
    sel_headers = get_switches(param_list) # gets the text value of each selected header
    sel_headers = [str(header.split(":")[0][:-2]) for header in sel_headers] # removes everything after the ':', [:-2] removes the 2 extra spaces I added
    headers = list(set(req_headers).union(sel_headers)) # combine required and selected headers without duplication

    # Get analysis and paramCurrent dataframes from custom function
    analysis_df, paramCurrent_df = get_dataframes(headers)
    
    # Define ts and attr headers
    first_df = analysis_df.get_group(list(analysis_df.groups.keys())[0]) # define df for first weld to determine headers
    print(first_df[headers])
    attr_headers, ts_headers = identify_attr(first_df[headers]) # get ts/attr headers from first weld
    non_msec_ts_headers = [header for header in ts_headers if header != msec] # contains all ts headers except Msec
    # DEBUG
    print("Attribute Headers: ", attr_headers)
    print("Time Series Headers: ", ts_headers)

    # map weld_id to schedule_id
    schedule_map = generate_schedule_map(analysis_df,paramCurrent_df)  # returns the group keys of each weld and it's matching schedule [weld, schedule]

    # Interpolate time series gaps and fill HDF5 file
    failed_welds = []
    all_ts_data = []
    all_attr_data = []
    for weld in tqdm(schedule_map, "Interpolating data"): # iterate through each weld (weld[0]: weld_id, weld[1]: schedule_id)
        # make separate variables for current data frames
        analysis = analysis_df.get_group(weld[0]).copy()
        schedule = paramCurrent_df.get_group(weld[1]).copy() # Get schedule for this weld as dataframe
        detail_mode = True if analysis[detail_mode_header].iloc[0] == 'Detail Mode' else False # determine if current weld is in detail mode

        # If user selects 'Detail-Mode Only'...
        if detail_mode_only_var.get() == 1:
            # Skip weld if not in detail mode
            if not detail_mode:
                continue # skip this weld and move to the next
            # ts_data without interpolating
            interp_data = [np.array(analysis[header]) for header in ts_headers]
            ts_headers_attr = [header for header in ts_headers] # create an array of headers in the same order as time series
            # add schedule if selected
            if include_schedule_var.get() == 1:
                interp_data.append(schedule[current_header_schedule].tolist())
                ts_headers_attr.append('Schedule')

        # If user hasn't selected 'Detail-Mode Only'...
        else:
            # Create offset array
            offset = 0
            offset_array = []
            zero_indices = []
            for i in range(len(schedule)): # iterate through each element of the schedule
                if schedule[current_header_schedule].iloc[i] == 0: # if the schedule current is 0...
                    offset += 1 # increment offset
                    zero_indices.append(i) # used to delete data points in detail mode
                else:
                    offset_array.append(offset) # add the current offset to the list of offsets

            # Process data: create gaps in the msec data where schedule current is 0
            if detail_mode: # If current weld is in Detail Mode...
                if len(schedule) != len(analysis): # check if schedule and analysis are same length
                    failed_welds.append(f"ERROR: Weld {weld[0]} (Detail Mode) has a schedule with {len(schedule)} data points and the analysis has {len(analysis)}")
                    continue # skip this weld and move to the next

                # Convert detail data to non-detail data
                analysis.reset_index(drop=True, inplace=True)  # This discards the old index and creates a new index
                analysis.drop(zero_indices, inplace=True) # remove each row from analysis where schedule=0
                    
            else: # not in detail mode
                # ensure offest_array and analysis are same length (no difference between detail and non-detail at this point)
                if len(offset_array) != len(analysis): # check if offset_array and analysis are the same length
                    failed_welds.append(f"ERROR: Weld {weld[0]} (Non-Detail Mode) has an offset array with {len(offset_array)} data points and the analysis has {len(analysis)}")
                    continue # skip this weld and move to the next
                
                # Add offset to original time series
                for i in range(len(analysis)): # iterate over each row in time series
                    analysis.loc[analysis.index[i], msec] += offset_array[i] # add the offset value to each Msec
                    

            # Fill gaps with interpolated data
            indexes = np.array(analysis[msec]) # create an array of msec time series for current weld
            data = [np.array(analysis[header]) for header in non_msec_ts_headers if header != current_header_analysis] # create list of arrays: ts data except msec and current
            ts_headers_attr = [header for header in non_msec_ts_headers if header != current_header_analysis] # create an array of headers in the same order as time series

            # Call interpolation function
            interp_indexes, interp_data = linear_interpolation(indexes,*data) # perform interpolation on missing data rows
            # interp_data is a list of arrays containing the time series for each selected header
            # interp_indexes is an array of indexes (aka Msec data). Should be complete 1,2,3,...,n

            # Generate 'Current' data (0 when schedule current is 0)
            if current_header_analysis in headers:
                new_current_data = add_zeros_at_missing_indexes(indexes,np.array(analysis[current_header_analysis])) # gets modified current data from custom function
                interp_data.append(new_current_data) # add modified current data to the interp_data array
                ts_headers_attr.append(current_header_analysis)
            # add msec if selected
            if msec in sel_headers:
                interp_data.append(interp_indexes)
                ts_headers_attr.append(msec)
            # add schedule if selected
            if include_schedule_var.get() == 1:
                schedule = schedule.iloc[:len(interp_indexes)] # set dimensions to match other data and reset index for some bs reason
                interp_data.append(schedule[current_header_schedule].tolist())
                ts_headers_attr.append('Schedule')

        # Create single time series data matrix
        try:
            ts_data = np.column_stack(interp_data) # stack the list of lists into a single 2D array
        except Exception as e:
            print("Error occured concatenating interpolated data:", e)
            # Debug printout
            for index, array in enumerate(interp_data):
                print("Array: ", index+1, " Length: ", len(array))
            print("Problem Weld: ", analysis[weld_id].iloc[0])
            print("Problem DOE: ", analysis['# for DoE Based Model'].iloc[0])
            break # exit main for loop
        
        # create array to store values for each header in attr_headers
        attr_data = [(DOE_header,analysis[DOE_header].iloc[0]),(weld_id, analysis[weld_id].iloc[0])] # Initialize attr_data (ensure DOE# and Weld_ID are first in)
        for header in attr_headers: # For each attribute header...
            if not DOE_header or weld_id:
                attr_data.append((header, analysis[header].iloc[0])) # Add attribute and related header to attr_data
        attr_data.append(('headers',ts_headers_attr)) # include the array of headers to attributes

        # add ts and attr data to their respective master lists
        all_ts_data.append(ts_data) # add time series data to list
        all_attr_data.append(attr_data) # add attribute data to list

    # Create HDF5 File
    output_path = os.path.join(entry_1.get(), "Database_out.h5")
    print(f"Saving HDF5 to {output_path}...")
    with h5py.File(output_path, "w") as file: # define new HDF5 file in write mode
         for i in range(len(all_ts_data)):
            # create dataset for current weld with ts data
            dataset_name = str(all_attr_data[i][0][1]) + ", " + str(all_attr_data[i][1][1]) # define dataset name (DOE#, Weld#)
            dataset = file.create_dataset(dataset_name, data=all_ts_data[i])
            # add attributes to dataset
            for header, attr in all_attr_data[i]:
                if (header in sel_headers) or (header == 'headers'): # if a user selected header or it's the 'headers' attribute
                    dataset.attrs[header] = attr # Add attribute to current dataset
    
    # Complete message
    if len(failed_welds) > 0:
        for fail_message in failed_welds:
            print(fail_message)
        print(f"Completed with {len(failed_welds)} failed welds.")
    else:
        print(f"Successfully saved HDF5.")


# GRAPHICAL ELEMENTS ==========================================================================================================

# Define graphial window
customtkinter.set_appearance_mode("dark")  # Modes: "System" (standard), "Dark", "Light"
customtkinter.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"
app = customtkinter.CTk()
app.geometry("600x1000")
app.title("DOE to Database")

# Main Frame
frame_1 = customtkinter.CTkFrame(master=app)
frame_1.pack(pady=20, padx=60, fill="both", expand=True)

# Top Label
label_1 = customtkinter.CTkLabel(master=frame_1,text="Configure Database", justify=customtkinter.LEFT)
label_1.pack(pady=10, padx=10)

# Filepath TextBox
entry_1 = customtkinter.CTkEntry(master=frame_1, placeholder_text="DOE Filepath...")
entry_1.pack(fill=tk.X,pady=10, padx=20)
# Browse button
browse_button = customtkinter.CTkButton(master=frame_1, text="Browse",command=browse_file)
browse_button.pack(pady=10, padx=10)

# create DOE List scrollable frame
DOEList = customtkinter.CTkScrollableFrame(master=frame_1,label_text="Data Sets")
DOEList.pack(fill=tk.X, pady=10, padx=10)

# create Parameter List scrollable frame
param_list = customtkinter.CTkScrollableFrame(master=frame_1,label_text="Parameters")
param_list.pack(fill=tk.X, pady=10, padx=10)

# Checkbox for including schedule
include_schedule_var = tk.IntVar()
include_schedule_checkbox = customtkinter.CTkCheckBox(master=frame_1, text="Include Welding Schedule", variable=include_schedule_var)
include_schedule_checkbox.pack(pady=10, padx=10)

# Detail mode only checkbox
detail_mode_only_var = tk.IntVar()
include_padding_checkbox = customtkinter.CTkCheckBox(master=frame_1, text="Detail-Mode only", variable=detail_mode_only_var)
include_padding_checkbox.pack(pady=10, padx=10)

# Submit Button
button_1 = customtkinter.CTkButton(master=frame_1, text="Generate HDF5", command=submit_button)
button_1.pack(pady=10, padx=10)

# Loading Bar
progressbar_1 = customtkinter.CTkProgressBar(master=frame_1)
progressbar_1.pack(pady=10, padx=10)
progressbar_1.set(0)

app.mainloop()