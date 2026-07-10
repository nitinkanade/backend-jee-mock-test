import os
import json

# Dynamically resolve backend directory relative to this script
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(BACKEND_DIR, "manifest.json")

def fix_paper(filepath, paper_id):
    print(f"Fixing paper: {os.path.basename(filepath)}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return

    modified = False
    
    # Traverse sections and subsections to fix questions
    sections = data.get('sections', [])
    for sec in sections:
        # Section questions
        sec_qs = sec.get('questions', [])
        fixed_qs = []
        for q in sec_qs:
            q_id = q.get('id')
            # Check if this is the invalid chem_q20 question to remove
            if paper_id == "2024_mains_jan_29_s1" and q_id == "chem_q20":
                print(f"  Removing invalid question: {q_id}")
                modified = True
                continue
                
            # Fix missing negativeMarks
            if 'negativeMarks' not in q:
                print(f"  Adding missing negativeMarks (0) to question: {q_id}")
                q['negativeMarks'] = 0
                modified = True
                
            fixed_qs.append(q)
        sec['questions'] = fixed_qs
                
        # Subsections questions
        subsections = sec.get('subsections', [])
        for sub in subsections:
            sub_qs = sub.get('questions', [])
            fixed_sub_qs = []
            for q in sub_qs:
                q_id = q.get('id')
                # Check if this is the invalid chem_q20 question to remove
                if paper_id == "2024_mains_jan_29_s1" and q_id == "chem_q20":
                    print(f"  Removing invalid question: {q_id}")
                    modified = True
                    continue
                    
                # Fix missing negativeMarks
                if 'negativeMarks' not in q:
                    print(f"  Adding missing negativeMarks (0) to question: {q_id}")
                    q['negativeMarks'] = 0
                    modified = True
                    
                fixed_sub_qs.append(q)
            sub['questions'] = fixed_sub_qs

    if modified:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"  Successfully saved changes to {os.path.basename(filepath)}")
        except Exception as e:
            print(f"  Error saving changes to {filepath}: {e}")
    else:
        print("  No changes needed.")

def run_fixer():
    if not os.path.exists(MANIFEST_PATH):
        print(f"Error: manifest.json not found at {MANIFEST_PATH}")
        return

    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        manifest_data = json.load(f)
        
    papers_list = manifest_data.get('papers', [])
    
    for paper in papers_list:
        if paper.get('comingSoon') is True:
            continue
            
        filename_rel = paper.get('filename')
        if not filename_rel:
            continue
            
        filepath = os.path.join(BACKEND_DIR, filename_rel)
        if os.path.exists(filepath):
            fix_paper(filepath, paper['id'])

if __name__ == "__main__":
    run_fixer()
