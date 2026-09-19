import pandas as pd
from pathlib import Path
from openai import OpenAI
from pydantic import create_model

PDF_FOLDER  = "test"
PROMPT_PATH = "author_info_prompt.md"
MODEL       = "gpt-5.4-2026-03-05"
OUTPUT_PATH = "author_match_llm.csv"


client = OpenAI()
MAX_AUTHOR = 8

prompt = Path(PROMPT_PATH).read_text(encoding='utf-8')
fields = {}
for i in range(MAX_AUTHOR):
    fields[f'author_{i}'] = (str, None)
    fields[f'institution_{i}'] = (str, None)

Authors = create_model('Authors', **fields)


def extract_authors_from_pdfs(pdf_folder: str) -> pd.DataFrame:
    rows = []
    pdf_files = sorted(Path(pdf_folder).glob('*.pdf'))

    for pdf_path in pdf_files:
       
        data = pdf_path.read_bytes()
        if len(data) == 0 or data[:5] != b'%PDF-' or b'%%EOF' not in data[-1024:]:
            continue

        file = client.files.create(
            file=open(pdf_path, 'rb'),
            purpose='user_data'
        )

        response = client.responses.parse(
            model=MODEL,
            instructions=prompt,
            input=[
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'input_file',
                            'file_id': file.id
                        },
                        {
                            'type': 'input_text',
                            'text': 'Extract the author names and their institutions from this paper.'
                        }
                    ]
                }
            ],
            text_format=Authors
        )

        row = {'file_name': pdf_path.stem}
        row.update(response.output_parsed.model_dump())
        rows.append(row)

    columns = ['file_name']
    for i in range(MAX_AUTHOR):
        columns.append(f'author_{i}')
        columns.append(f'institution_{i}')

    return pd.DataFrame(rows, columns=columns)


if __name__ == '__main__':
    df = extract_authors_from_pdfs(PDF_FOLDER)
    df.to_csv(OUTPUT_PATH, index=False)
    print('finished')