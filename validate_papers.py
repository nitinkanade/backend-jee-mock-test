import os
import json
import re
import sys

# Dynamically resolve backend directory relative to this script
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(BACKEND_DIR, "manifest.json")

def check_latex_balance(text):
    if not text:
        return True, ""
    # Count unescaped single and double dollar signs
    double_dollars = len(re.findall(r'(?<!\\)\$\$', text))
    # Replace $$ temporarily to avoid double counting
    temp_text = text.replace('$$', '##')
    single_dollars = len(re.findall(r'(?<!\\)\$', temp_text))
    
    if double_dollars % 2 != 0:
        return False, "Unbalanced double dollar signs ($$)"
    if single_dollars % 2 != 0:
        return False, "Unbalanced single dollar signs ($)"
    return True, ""

def validate_question(q, paper_dir, paper_id):
    errors = []
    
    # Check ID
    q_id = q.get('id')
    if not q_id:
        errors.append("Missing 'id'")
    
    # Check type
    q_type = q.get('type')
    valid_types = {"single_correct", "multi_correct", "numerical", "matching"}
    if not q_type:
        errors.append("Missing 'type'")
    elif q_type not in valid_types:
        errors.append(f"Invalid 'type': '{q_type}' (must be one of {valid_types})")
        
    # Check questionText
    q_text = q.get('questionText')
    if not q_text or not q_text.strip():
        errors.append("Missing or empty 'questionText'")
    else:
        ok, err = check_latex_balance(q_text)
        if not ok:
            errors.append(f"LaTeX error in 'questionText': {err}")

    # Every published question must include a usable worked explanation.
    explanation = q.get('explanation')
    if not explanation or not isinstance(explanation, str) or not explanation.strip():
        errors.append("Missing or empty 'explanation'")
    else:
        ok, err = check_latex_balance(explanation)
        if not ok:
            errors.append(f"LaTeX error in 'explanation': {err}")

    # Check marks
    if 'marks' not in q:
        errors.append("Missing 'marks'")
    elif not isinstance(q['marks'], int):
        errors.append(f"Invalid 'marks': '{q['marks']}' (must be an integer)")
        
    # Check negativeMarks
    if 'negativeMarks' not in q:
        errors.append("Missing 'negativeMarks'")
    elif not isinstance(q['negativeMarks'], int):
        errors.append(f"Invalid 'negativeMarks': '{q['negativeMarks']}' (must be an integer)")

    # Check images
    has_image = q.get('hasImage', False)
    image_name = q.get('imageName')
    if has_image:
        if not image_name:
            errors.append("hasImage is true but 'imageName' is missing")
        else:
            image_path = os.path.join(paper_dir, image_name)
            if not os.path.exists(image_path):
                errors.append(f"Referenced image file not found: '{image_name}' (expected at '{image_path}')")
    elif image_name:
        errors.append(f"hasImage is false but 'imageName' is specified ('{image_name}')")

    # Check type-specific properties
    if q_type == 'single_correct' or q_type == 'multi_correct':
        options = q.get('options')
        if not options:
            errors.append("Missing 'options' for MCQ type")
        elif not isinstance(options, list):
            errors.append("'options' must be a list")
        else:
            correct_count = 0
            for idx, opt in enumerate(options):
                opt_id = opt.get('id')
                opt_text = opt.get('text')
                if not opt_id:
                    errors.append(f"Option {idx} missing 'id'")
                if not opt_text or not opt_text.strip():
                    errors.append(f"Option {idx} ({opt_id}) has empty 'text'")
                else:
                    ok, err = check_latex_balance(opt_text)
                    if not ok:
                        errors.append(f"LaTeX error in option {opt_id}: {err}")
                if opt.get('isCorrect') is True:
                    correct_count += 1
            
            if q_type == 'single_correct':
                if correct_count != 1:
                    errors.append(f"single_correct question must have exactly 1 correct option (found {correct_count})")
            elif q_type == 'multi_correct':
                if correct_count < 1:
                    errors.append(f"multi_correct question must have at least 1 correct option (found {correct_count})")

    elif q_type == 'numerical':
        if 'answer' not in q:
            errors.append("Missing 'answer' for numerical question")
        else:
            answer = q['answer']
            if answer is None or str(answer).strip() == "":
                errors.append("Numerical 'answer' is empty")

    elif q_type == 'matching':
        listI = q.get('listI')
        listII = q.get('listII')
        options = q.get('options')
        
        if not q.get('hideTextLists'):
            if not listI:
                errors.append("Missing or empty 'listI' for matching question")
            if not listII:
                errors.append("Missing or empty 'listII' for matching question")
                
        if not options:
            errors.append("Missing 'options' for matching question")
        elif not isinstance(options, list):
            errors.append("'options' must be a list")
        else:
            correct_count = 0
            for idx, opt in enumerate(options):
                opt_id = opt.get('id')
                opt_text = opt.get('text')
                if not opt_id:
                    errors.append(f"Option {idx} missing 'id'")
                if not opt_text or not opt_text.strip():
                    errors.append(f"Option {idx} ({opt_id}) has empty 'text'")
                if opt.get('isCorrect') is True:
                    correct_count += 1
            if correct_count != 1:
                errors.append(f"matching question must have exactly 1 correct combination option (found {correct_count})")
                
    return errors

def validate_paper(filepath):
    paper_dir = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    
    print(f"Analyzing paper: {filename}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as je:
        return False, {"json_error": f"Invalid JSON syntax: {je}"}, []
    except Exception as e:
        return False, {"file_error": f"Failed to read file: {e}"}, []

    paper_errors = {}
    total_questions = 0
    questions_to_remove = []

    # Traverse sections and subsections to find questions
    sections = data.get('sections', [])
    for sec_idx, sec in enumerate(sections):
        # Section questions
        sec_qs = sec.get('questions', [])
        for q_idx, q in enumerate(sec_qs):
            total_questions += 1
            q_id = q.get('id', f"Q_{q_idx}")
            errs = validate_question(q, paper_dir, data.get('examTitle'))
            if errs:
                paper_errors[q_id] = errs
                questions_to_remove.append((sec, q, q_id))
                
        # Subsections questions
        subsections = sec.get('subsections', [])
        for sub_idx, sub in enumerate(subsections):
            sub_qs = sub.get('questions', [])
            for q_idx, q in enumerate(sub_qs):
                total_questions += 1
                q_id = q.get('id', f"Q_{q_idx}")
                errs = validate_question(q, paper_dir, data.get('examTitle'))
                if errs:
                    paper_errors[q_id] = errs
                    questions_to_remove.append((sub, q, q_id))
                    
    return True, paper_errors, questions_to_remove

def validate_manifest_entry(paper, seen_ids):
    errors = []
    paper_id = paper.get('id')
    if not paper_id:
        errors.append("Missing 'id'")
    elif paper_id in seen_ids:
        errors.append(f"Duplicate paper id: '{paper_id}'")
    else:
        seen_ids.add(paper_id)
    if not paper.get('title'):
        errors.append("Missing 'title'")
    if not isinstance(paper.get('year'), int):
        errors.append("Missing or non-integer 'year'")
    if 'version' in paper and not isinstance(paper['version'], int):
        errors.append(f"'version' must be an integer (found {paper['version']!r})")
    if paper.get('comingSoon') is not True and not paper.get('filename'):
        errors.append("Missing 'filename' on a paper that is not comingSoon")
    return errors

def run_validation():
    if not os.path.exists(MANIFEST_PATH):
        print(f"Error: manifest.json not found at {MANIFEST_PATH}")
        return False

    try:
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)
    except json.JSONDecodeError as je:
        print(f"CRITICAL: manifest.json is not valid JSON: {je}")
        return False

    papers_list = manifest_data.get('papers', [])
    all_errors = {}
    manifest_errors = []
    critical_errors = []
    seen_ids = set()

    for paper in papers_list:
        entry_errors = validate_manifest_entry(paper, seen_ids)
        if entry_errors:
            label = paper.get('id') or paper.get('title') or 'unknown entry'
            manifest_errors.append((label, entry_errors))

        if paper.get('comingSoon') is True:
            continue

        filename_rel = paper.get('filename')
        if not filename_rel:
            continue

        filepath = os.path.join(BACKEND_DIR, filename_rel)
        if not os.path.exists(filepath):
            critical_errors.append(f"Paper file not found: {filepath}")
            continue

        ok, errors, to_remove = validate_paper(filepath)
        if errors:
            all_errors[paper['id']] = (filepath, errors, to_remove)

    print("\n" + "="*50)
    print("VALIDATION SUMMARY")
    print("="*50)
    passed = not all_errors and not manifest_errors and not critical_errors
    if passed:
        print("All papers and questions are fully valid! No issues found.")
    else:
        for msg in critical_errors:
            print(f"\nCRITICAL: {msg}")
        for label, errs in manifest_errors:
            print(f"\nManifest entry: {label}")
            for e in errs:
                print(f"  - {e}")
        for paper_id, (filepath, errs, to_remove) in all_errors.items():
            print(f"\nPaper ID: {paper_id} ({os.path.basename(filepath)})")
            if "json_error" in errs:
                print(f"  CRITICAL: {errs['json_error']}")
            elif "file_error" in errs:
                print(f"  CRITICAL: {errs['file_error']}")
            else:
                for q_id, q_errs in errs.items():
                    print(f"  Question: {q_id}")
                    for e in q_errs:
                        print(f"    - {e}")
                print(f"  Total questions with issues: {len(errs)}")
        print("\nFix issues or run python fix_papers.py (if available) before committing.")
    return passed

if __name__ == "__main__":
    sys.exit(0 if run_validation() else 1)
