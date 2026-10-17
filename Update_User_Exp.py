from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import os


def set_aptos(paragraph, bold=False, underline=False):
    for run in paragraph.runs:
        run.font.name = "Aptos"
        run.font.size = Pt(11)
        run.bold = bold
        run.underline = underline


def create_user_experience_doc():
    # -------------------------------
    # User Inputs
    # -------------------------------
    app_name = input("Enter App Name: ")
    app_id = input("Enter App ID: ")
    description = input("Enter App Description: ")
    dependency = input("Enter Dependency (Enter NA if not applicable): ").strip()
    supersedence = input("Enter Supersedence App Name (Enter NA if not applicable): ").strip()

    # -------------------------------
    # Save Path
    # -------------------------------
    base_path = r"C:\Users\HCL0190\OneDrive - Allianz\Desktop\App Artifacts"

    # Create App ID folder if it doesn't exist
    save_path = os.path.join(base_path, app_id)
    os.makedirs(save_path, exist_ok=True)

    document = Document()

    # -------------------------------
    # App Name + Version (Centered, Bold, Underlined)
    # -------------------------------
    title_para = document.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(f"{app_name}")
    title_run.bold = True
    title_run.underline = True
    title_run.font.name = "Aptos"
    title_run.font.size = Pt(16)

    document.add_paragraph()

    # -------------------------------
    # Description (Centered, No Heading)
    # -------------------------------
    desc_para = document.add_paragraph(description)
    desc_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_aptos(desc_para)

    document.add_paragraph()
    document.add_paragraph()

    # -------------------------------
    # Dependency & Supersedence Logic
    # -------------------------------
    dep = dependency.upper()
    sup = supersedence.upper()

    if dep == "NA" and sup != "NA":
        package_line = (
            f'This application is a standalone package, and will be '
            f'superseding the older versions of "{supersedence}".'
        )
    elif dep == "NA" and sup == "NA":
        package_line = "This application is a standalone package."
    elif dep != "NA" and sup == "NA":
        package_line = f'This application needs a dependency of "{dependency}".'
    elif dep != "NA" and sup != "NA":
        package_line = (
            f'This application needs a dependency of "{dependency}".'
            f'superseding the older versions of "{supersedence}".'
        ) 

    p = document.add_paragraph(package_line)
    set_aptos(p)

    # -------------------------------
    # Static Content
    # -------------------------------
    static_lines = [
        "The installation would be auto push and the users will be receiving prompts as below.",
        (
            "Note: The entire installation may take 05 mins of your time. "
            "User will get ADT Prompt if older version application is running. "
            "User has to click on close and install then new version will install silently."
        ),
        "",
        "Notifications to users -",
        "1. Balloon Notification for download/Update & install.",
        "",
        "2. On Device - Balloon Notification for installation Complete.",
        "",
        "3. Post installation, you can see the add remove program",
        "",
        "Application shortcut will show like this -",
        ""
    ]

    for line in static_lines:
        para = document.add_paragraph(line)
        set_aptos(para)

    document.add_paragraph()

    # -------------------------------
    # AO Testing Statement (Centered, Bold)
    # -------------------------------
    ao_para = document.add_paragraph("AO will be testing the application functionality")
    ao_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_aptos(ao_para, bold=True)

    star_para = document.add_paragraph("****************************")
    star_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_aptos(star_para, bold=True)

    # -------------------------------
    # Save Document
    # -------------------------------
    file_name = f"{app_id}_{app_name}_User_Experience.docx"
    full_path = os.path.join(save_path, file_name)
    document.save(full_path)

    print(f"\n✅ Document created successfully at:\n{full_path}")


if __name__ == "__main__":
    create_user_experience_doc()