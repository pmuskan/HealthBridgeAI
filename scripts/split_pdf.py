import PyPDF2
import os

def split_pdf(input_path, output_folder, pages_per_chunk=80):
    os.makedirs(output_folder, exist_ok=True)
    reader = PyPDF2.PdfReader(input_path)
    total_pages = len(reader.pages)
    filename = os.path.splitext(os.path.basename(input_path))[0]
    
    for i in range(0, total_pages, pages_per_chunk):
        writer = PyPDF2.PdfWriter()
        for j in range(i, min(i + pages_per_chunk, total_pages)):
            writer.add_page(reader.pages[j])
        
        output_path = f"{output_folder}/{filename}_part{i//pages_per_chunk + 1}.pdf"
        with open(output_path, "wb") as f:
            writer.write(f)
        print(f"Created: {output_path}")

# Split the two large files
split_pdf("C:\\GenAI\HealthBridgeAI\\HealthBridgedoc\\2022, CURRENT Medical Diagnosis and Treatment- Original.pdf, CURRENT Medical Diagnosis and Treatment- Original.pdf", "C:\\GenAI\\HealthBridgeAI\\HealthBridgedoc\\split")
split_pdf("C:\\GenAI\HealthBridgeAI\\HealthBridgedoc\\Handbook for ASHA Facilitators and MPWs on HBNC and HBYC.pdf", "C:\\GenAI\\HealthBridgeAI\\HealthBridgedoc\\split")

print("Done splitting!")