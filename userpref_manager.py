import os
import sys
import json
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QComboBox, QPushButton, QListWidget, 
                               QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox)
from PySide6.QtCore import Qt

try:
    _dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _dir = os.path.dirname(os.path.abspath(sys.argv[0]))

davinci_dir = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\davinciFlow"
if os.path.exists(davinci_dir):
    CONFIG_PATH = os.path.join(davinci_dir, "davinciFlow_config.json")
else:
    CONFIG_PATH = os.path.join(_dir, "davinciFlow_config.json")

USERPREF_DIR = os.path.join(os.path.expanduser("~"), ".flowDavinciData")
if not os.path.exists(USERPREF_DIR):
    os.makedirs(USERPREF_DIR, exist_ok=True)
USERPREF_PATH = os.path.join(USERPREF_DIR, "userpref.json")

class UserPrefManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DaVinci Flow - User Preferences Manager")
        self.resize(600, 500)
        
        self.master_tasks = self.load_master_tasks()
        
        # Main Widget and Layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # --- Section: Preset Builder ---
        builder_label = QLabel("<b>Create / Edit Preset</b>")
        main_layout.addWidget(builder_label)
        
        # Preset Name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Preset Name:"))
        self.preset_name_input = QLineEdit()
        self.preset_name_input.setPlaceholderText("e.g. Compositor Default")
        name_layout.addWidget(self.preset_name_input)
        main_layout.addLayout(name_layout)
        
        # Add Task
        task_layout = QHBoxLayout()
        task_layout.addWidget(QLabel("Select Task:"))
        self.task_combo = QComboBox()
        self.task_combo.addItems(self.master_tasks)
        task_layout.addWidget(self.task_combo)
        
        self.add_task_btn = QPushButton("Add Task")
        self.add_task_btn.clicked.connect(self.add_task)
        task_layout.addWidget(self.add_task_btn)
        main_layout.addLayout(task_layout)
        
        # Current Task Sequence
        main_layout.addWidget(QLabel("Current Task Sequence:"))
        self.task_list = QListWidget()
        main_layout.addWidget(self.task_list)
        
        # Save Button
        self.save_btn = QPushButton("Save Preset")
        self.save_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self.save_btn.clicked.connect(self.save_preset)
        main_layout.addWidget(self.save_btn)
        
        main_layout.addSpacing(20)
        
        # --- Section: View Presets ---
        view_layout = QHBoxLayout()
        view_label = QLabel("<b>Existing Presets</b>")
        view_layout.addWidget(view_label)
        
        self.refresh_btn = QPushButton("View / Refresh Prefs")
        self.refresh_btn.clicked.connect(self.load_presets_to_table)
        view_layout.addWidget(self.refresh_btn)
        main_layout.addLayout(view_layout)
        
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Preset Name", "Task Sequence"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        main_layout.addWidget(self.table)
        
        # Initial Load
        self.load_presets_to_table()

    def load_master_tasks(self):
        tasks = ["delivery", "confo_render", "compo_comp", "compo_precomp", 
                 "light_precomp", "anim_main", "layout_base", "previz_base", "editing_edt"]
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                    tasks = config.get("tasks", tasks)
            except Exception as e:
                print(f"Failed to load master tasks from config: {e}")
        return tasks

    def add_task(self):
        task = self.task_combo.currentText()
        if not task:
            return
            
        # Check for duplicates
        for i in range(self.task_list.count()):
            if self.task_list.item(i).text() == task:
                QMessageBox.warning(self, "Duplicate Task", f"The task '{task}' is already in the sequence.")
                return
                
        self.task_list.addItem(task)
        
    def save_preset(self):
        preset_name = self.preset_name_input.text().strip()
        if not preset_name:
            QMessageBox.warning(self, "Missing Name", "Please enter a preset name.")
            return
            
        if self.task_list.count() == 0:
            QMessageBox.warning(self, "Empty Sequence", "Please add at least one task to the sequence.")
            return
            
        task_sequence = [self.task_list.item(i).text() for i in range(self.task_list.count())]
        
        # Load existing json
        data = {"presets": {}}
        if os.path.exists(USERPREF_PATH):
            try:
                with open(USERPREF_PATH, 'r') as f:
                    data = json.load(f)
            except:
                data = {"presets": {}}
                
        # Update and save
        data["presets"][preset_name] = task_sequence
        try:
            with open(USERPREF_PATH, 'w') as f:
                json.dump(data, f, indent=2)
            QMessageBox.information(self, "Success", f"Preset '{preset_name}' saved successfully!")
            self.preset_name_input.clear()
            self.task_list.clear()
            self.load_presets_to_table()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save preset: {e}")

    def load_presets_to_table(self):
        self.table.setRowCount(0)
        if not os.path.exists(USERPREF_PATH):
            return
            
        try:
            with open(USERPREF_PATH, 'r') as f:
                data = json.load(f)
                presets = data.get("presets", {})
                
            self.table.setRowCount(len(presets))
            for row, (name, tasks) in enumerate(presets.items()):
                self.table.setItem(row, 0, QTableWidgetItem(name))
                self.table.setItem(row, 1, QTableWidgetItem(", ".join(tasks)))
        except Exception as e:
            print(f"Failed to load presets for table: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UserPrefManager()
    window.show()
    sys.exit(app.exec())
