# database_visualizer.py
# Ethan York
# Dr. Wang
# University of Kentucky
# 11/10/2023

# DATABASE VISUALIZER
# GUI designed to visulize the data stored in an HDF5 created by the Database Creation Tool

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import customtkinter as ctk
import tkinter as tk
import numpy as np
import h5py

# Global Variable
weld_data = {}

# FUNCTIONS ===================================================================================================================

# LOAD HDF5
def load_hdf5(file_path):
    with h5py.File(file_path, 'r') as file:
        # Assuming each dataset in HDF5 represents a weld
        welds = {weld: {"data": np.array(file[weld]), "attrs": dict(file[weld].attrs)} for weld in file.keys()}
    return welds

# Function to update the wraplength of labels
def update_label_wraplength():
    frame_width = attr_frame.winfo_width()
    for label in attr_frame.winfo_children():
        if isinstance(label, ctk.CTkLabel):
            label.configure(wraplength=frame_width - 20)

# Function is a callthrough to the update graph function
def switch_changed_event_handler(event):
    update_graph()

# GET ACTIVE SWITCHES
# Takes in a Frame object and returns the active switches
def get_switches(parent: ctk.CTkFrame):
    active_switches = []
    for switch in parent.winfo_children():
        if switch.get() == 1:
            active_switches.append(switch.cget('text'))
    return(active_switches)

# clear frame
def clear_frame(frame):
    for widget in frame.winfo_children():
        widget.destroy()

# BROWSE BUTTON PRESSED
def browse_file():
    global weld_data # Reference the global variable

    # Define the file types
    file_types = [('HDF5 files', '*.h5')]

    # Open the file dialog with specified file types
    folder_path = tk.filedialog.askopenfilename(filetypes=file_types)
    filepath_box.delete(0, ctk.END) # clear the textbox
    filepath_box.insert(0,folder_path) # insert file_path from file dialog

    # Load data and populate the combobox, only if a file was selected
    if folder_path:
        weld_data = load_hdf5(folder_path)
        weld_combobox['values'] = list(weld_data.keys())

# FILL GRAPH SWITCH FRAME
def fill_switch_frame(headers):
    clear_frame(switch_frame) # Clear frame
    
    # Add switches
    for header in headers:
        switch = ctk.CTkSwitch(master=switch_frame, text=header)
        switch.pack(side=tk.LEFT, padx=10, pady=10)
        switch.toggle()
        switch.bind("<ButtonRelease-1>", switch_changed_event_handler)  # trigger function when switch is changed

# UPDATE ATTRIBUTES
def update_attributes():
    global selected_weld # reference global variable
    clear_frame(attr_frame) # Clear frame

    attr_data = weld_data[selected_weld]["attrs"]
    row = 0 # start at first row
    for attr, value in attr_data.items():
        value = ', '.join(value) if attr == 'headers' else str(value) # convert heaaders array to single string
        label_text = f"{attr}: {value}" # combine key and value to single string for display
        label = ctk.CTkLabel(master=attr_frame, text=label_text, anchor='w', justify='left') # anchor west, justify new lines left
        label.grid(row=row, column=0, padx=10, pady=5, sticky="w") # grid sticks west
        row += 1 # increment row

# WELD SELECTED
def on_weld_select(event):
    global selected_weld # reference global variable
    selected_weld = weld_combobox.get() # get weld from combomox selection
    headers = weld_data[selected_weld]["attrs"].get("headers", []) # get headers from attributes of current weld
    if len(switch_frame.winfo_children()) == 0: # only create switches if there aren't any switches already
        fill_switch_frame(headers) # load the parameter switches
    update_graph() # call update graph

# ON CLOSING
def on_closing():
    plt.close('all')
    app.quit()

# UPDATE GRAPH
def update_graph():
    global weld_data, selected_weld  # Reference the global variable

    # Clear previous figure/attributes
    plt.close('all')
    clear_frame(graph_frame) # clear graph frame

    # Check if weld data is available
    if selected_weld not in weld_data:
        print(f"No data available for weld: {selected_weld}")
        return # exit function

    update_attributes() # Update attribute information

    # Create new figures for the chart and legend
    fig_chart, ax1 = plt.subplots()
    fig_legends, ax_legends = plt.subplots()
    ax2 = ax1.twinx()  # Create a secondary axis sharing the same x-axis
    data = weld_data[selected_weld]["data"]
    headers = weld_data[selected_weld]["attrs"].get("headers", [])
    sel_headers = get_switches(switch_frame)

    # Define color sets for the two axes
    primary_axis_colors = plt.cm.viridis(np.linspace(0, 1, data.shape[1]))
    secondary_axis_colors = plt.cm.plasma(np.linspace(0, 1, data.shape[1]))

    # Plotting
    handles = []  # List to store handles
    for col in range(data.shape[1]):
        # check if user selected current parameter
        if headers[col] not in sel_headers:
            continue # skip this iteration of the for loop
        
        # verify there is a header for each column
        if len(headers) != data.shape[1]:
            print(f"ERROR: there are {len(headers)} headers and {data.shape[1]} columns of time series data")
            break

        # Check if any data point in the column exceeds 3000
        if np.any(data[:, col] > 3000):
            color = secondary_axis_colors[col]
            line, = ax2.plot(data[:, col], color=color, label=headers[col] + " (right axis)")
            handles.append(line)
        else:
            color = primary_axis_colors[col]
            line, = ax1.plot(data[:, col], color=color, label=headers[col])
            handles.append(line)

    # Set labels and titles (modify as needed)
    ax1.set_xlabel("Time (ms)")
    ax1.set_ylabel("Other Values")
    ax2.set_ylabel("Current")

    # Adding the legends to ax_legends
    ax_legends.legend(handles, [h.get_label() for h in handles])

    # Remove axes from ax_legends
    ax_legends.axis('off')

    # Embed the figure in the Tkinter window
    canvas = FigureCanvasTkAgg(fig_chart, master=graph_frame)
    canvas_widget = canvas.get_tk_widget()
    canvas_widget.pack(fill=tk.BOTH, expand=True)
    canvas.draw()

    # Embed the legends figure in the Tkinter window
    canvas_legends = FigureCanvasTkAgg(fig_legends, master=graph_frame)  # Embed fig_legends in the same graph_frame
    canvas_widget_legends = canvas_legends.get_tk_widget()
    canvas_widget_legends.pack(fill=tk.BOTH, expand=True)
    canvas_legends.draw()

# GRAPHICAL ELEMENTS ==========================================================================================================

# Define graphial window
ctk.set_appearance_mode("dark")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"
app = ctk.CTk()
app.geometry("1600x850")
app.title("Database Visualizer")

# Main Frame
main_frame = ctk.CTkFrame(master=app)
main_frame.grid(row=0, column=0, pady=20, padx=20, sticky="nsew")

# Right Frame
right_frame = ctk.CTkFrame(master=app)
right_frame.grid(row=0, column=1, pady=20, padx=20, sticky="nsew")

# Configure the grid columns
app.grid_columnconfigure(0, weight=2)  # This makes the main_frame expandable
app.grid_columnconfigure(1, weight=1)  # This makes the right_frame expandable
app.grid_rowconfigure(0, weight=1)  # Makes row 0 expandable


# File Select Frame: Container for Top Label, Filepath TextBox, and Browse button 
file_select_frame = ctk.CTkFrame(master=main_frame)
file_select_frame.pack(pady=10, padx=10, fill=ctk.X)

# Top Label
label_1 = ctk.CTkLabel(master=file_select_frame, text="HDF5 File:", justify=ctk.LEFT)
label_1.pack(side=ctk.LEFT, padx=(10, 10))  # Align to the left

# Filepath TextBox
filepath_box = ctk.CTkEntry(master=file_select_frame, placeholder_text="DOE Filepath...")
filepath_box.pack(side=ctk.LEFT, fill=ctk.X, expand=True)  # Expand to fill the space

# Browse button
browse_button = ctk.CTkButton(master=file_select_frame, text="Browse", command=browse_file)
browse_button.pack(side=ctk.LEFT, padx=(10, 0))  # Align to the left

# Combobox for weld selection
weld_combobox = tk.ttk.Combobox(master=main_frame)
weld_combobox.pack(pady=10, padx=10)
weld_combobox.bind("<<ComboboxSelected>>", on_weld_select)

# Frame for graph switches
switch_frame = ctk.CTkFrame(master=main_frame)
switch_frame.pack(fill=ctk.BOTH, expand=True, pady=10, padx=10)

# Frame for Matplotlib graph
graph_frame = ctk.CTkFrame(master=main_frame)
graph_frame.pack(fill=ctk.BOTH, expand=True, pady=10, padx=10)

# Attribute scrollable frame
attr_frame = ctk.CTkScrollableFrame(master=right_frame,label_text="Attributes")
attr_frame.pack(fill=ctk.BOTH, pady=10, padx=10, expand=True)
attr_frame.bind("<Configure>", lambda event: update_label_wraplength())

# Suppress Combobox scrolling error message
def custom_report_callback_exception(exc, val, tb):
    if isinstance(val, AttributeError) and str(val) == "'str' object has no attribute 'master'":  
        pass # Ignore specific AttributeError
    else: # For all other exceptions... 
        original_report_callback_exception(exc, val, tb) # call the default report callback exception function
original_report_callback_exception = app.report_callback_exception # Save the original report_callback_exception function
app.report_callback_exception = custom_report_callback_exception # Override the report_callback_exception function

# closing
app.protocol("WM_DELETE_WINDOW", on_closing)
app.mainloop()