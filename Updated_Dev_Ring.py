import shutil
import os
from docx import Document
from datetime import datetime

# ---------------------------
# USER INPUT
# ---------------------------
apm_id = input("Enter APM ID: ")
app_name = input("Enter App Name: ")
description = input("Enter Description: ")
version = input("Enter Version: ")
ao_name = input("Enter AO Name: ")
detection = input("Enter Detection: ")
dependency = input("Enter Dependency: ")
supersedence = input("Enter Supersedence: ")

# Auto date
today_date = datetime.today().strftime("%m/%d/%Y")

# ---------------------------
# PATHS
# ---------------------------
source_file = r"C:\Users\HCL0190\OneDrive - Allianz\Desktop\Informations\Template.docx"

# Base location
base_folder = r"C:\Users\HCL0190\OneDrive - Allianz\Desktop\App Artifacts"

# Create APM ID folder if it doesn't exist
destination_folder = os.path.join(base_folder, apm_id)
os.makedirs(destination_folder, exist_ok=True)

temp_file = os.path.join(destination_folder, "temp.docx")

final_file = os.path.join(
    destination_folder,
    f"{apm_id}_{app_name}_Dev_Ring.docx"
)

# ---------------------------
# COPY TEMPLATE
# ---------------------------
shutil.copy(source_file, temp_file)

# ---------------------------
# REPLACEMENTS
# ---------------------------
replacements = {
    "{{APP_NAME}}": app_name,
    "{{APM_ID}}": apm_id,
    "{{VERSION}}": version,
    "{{SUPERSEDENCE}}": supersedence,
    "{{DEPENDENCY}}": dependency,
    "{{DESCRIPTION}}": description,
    "{{DETECTION}}": detection,
    "{{AO_NAME}}": ao_name,
    "{{DATE}}": today_date,
}

# ---------------------------
# FORMATTING-SAFE REPLACEMENT
# ---------------------------
def replace_text_preserve_format(container):
    for paragraph in container.paragraphs:
        runs = paragraph.runs
        if not runs:
            continue

        full_text = "".join(run.text for run in runs)

        replaced = False
        for key, value in replacements.items():
            if key in full_text:
                full_text = full_text.replace(key, value)
                replaced = True

        if replaced:
            # Update text run-by-run while preserving formatting
            idx = 0
            for run in runs:
                run_len = len(run.text)
                run.text = full_text[idx: idx + run_len]
                idx += run_len

            # Any remaining text goes to the last run
            if idx < len(full_text):
                runs[-1].text += full_text[idx:]

    for table in container.tables:
        for row in table.rows:
            for cell in row.cells:
                replace_text_preserve_format(cell)

# ---------------------------
# EDIT DOCUMENT
# ---------------------------
doc = Document(temp_file)
replace_text_preserve_format(doc)
doc.save(temp_file)

# ---------------------------
# RENAME FILE
# ---------------------------
os.rename(temp_file, final_file)

print("\n✅ COMPLETED SUCCESSFULLY")
print("📄 File:", final_file)
print("🎨 Formatting preserved exactly as template")