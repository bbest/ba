
# initially based on: 
# - [cstories-app/api: main.py](https://github.com/cstories-app/api/blob/b87eeb5250a05e005473f1f40589a7a04830561a/main.py)
# - without fastapi part
# Google Python modules:
# pip3.10 install --upgrade \
#       tiktoken \
#       openai \
#       python-dotenv \
#       google-auth \
#       google-api-python-client \
#       google-auth-httplib2 \
#       google-auth-oauthlib

import os
from datetime import datetime
import openai # openai-0.27.2
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import io
from googleapiclient.http import MediaIoBaseDownload
import re
import tiktoken
import json

# paths
tags_txt      = 'tags.txt'
doc_tags_json = 'doc_tags.json'

# read tags from tags_txt
with open(tags_txt, 'r') as f:
    txt_tags = f.read().strip('\n')

# load OPENAI_API_KEY from .env
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
enc = tiktoken.encoding_for_model("text-davinci-003")

# load Google Service Account Key and Scopes
GKEY_JSON = os.getenv("PATH_GOOGLE_SA_KEY_JSON")
GSCOPES = [
  "https://www.googleapis.com/auth/drive",
  "https://www.googleapis.com/auth/drive.file",
  "https://www.googleapis.com/auth/spreadsheets"]
# GoogleDrive folder with Viewer permissions given to cstories-app-for-gsheets@cstories-app.iam.gserviceaccount.com
# - [ba - Google Drive](https://drive.google.com/drive/folders/1aXxKrkYJ4eI1reTL3kz3K0Qyrqtna1s-)

# create GoogleDrive client service
creds = service_account.Credentials.from_service_account_file(
  GKEY_JSON).with_scopes(GSCOPES)
drive = build('drive', 'v3', credentials = creds)

# https://stackoverflow.com/questions/56857760/list-of-files-in-a-google-drive-folder-with-python
ba_id = drive.files().list(
   q = "mimeType = 'application/vnd.google-apps.folder' and name = 'ba'"
   ).execute().get('files', [])[0].get('id')
results = drive.files().list(
   q = "mimeType = 'application/vnd.google-apps.document' and" +
   "'" + ba_id + "' in parents", 
   pageSize=100, fields="nextPageToken, files(id, name)").execute()
docs = results.get('files', [])

def get_txt_tags(txt_part, txt_tags, f_name = None, doc_tags_json = None):
  """Get tags for a text part."""
  #
  question = f"""
    The following is a list of tags:

    {txt_tags}

    Apply relevant tags to the following content:
    
    {txt_part}
    """
  #
  engine_max_tokens = 4097
  question_tokens = len(enc.encode(question))
  response_tokens = engine_max_tokens - question_tokens
  #
  if prompt_tokens < 100:
    tags = 'TEXT_TOO_LONG'
  else:
    response = openai.Completion.create(
        engine = 'text-davinci-003',
        prompt = question,
        max_tokens = response_tokens)
    tags_str = response.choices[0].text.strip().removeprefix(
      'Tags: ').removeprefix(
      'Relevant Tags: ')
    tags = re.split(', |,|\n|\r|\n\r|\r\n', tags_str)
  # continue with tags
  if doc_tags_json is not None and f_name is not None:
    # form dictionary element
    d = {
      "file_name": f_name,
      "text_excerpt": txt_part,
      "tags": tags}
    d_json = json.dumps(d)
    
    # if doc_tags_json does not exist, create it and write "[" at the beginning
    if not os.path.exists(doc_tags_json):
      with open(doc_tags_json, 'w') as f:
        f.write("[\n")

    # write dictionary element to doc_tags_json
    with open(doc_tags_json, 'a') as f:
      f.write(F"""
        {d_json},
        """)    
  return tags

# loop through all Gdocs in the folder
# for i in range(0, len(docs)): # i = 0
for i in range(0, 2): # i = 0  
  f_id = docs[i].get('id')
  f_name = docs[i].get('name')
  print(F'File {i}/{len(docs)} "{f_name}" with id "{f_id}"')
  req = drive.files().export_media(
    fileId   = f_id,
    mimeType = 'text/plain')
  fh = io.BytesIO()
  downloader = MediaIoBaseDownload(fh, req)
  done = False
  while done is False:
    status, done = downloader.next_chunk()
  # continue with the downloaded text
  txt = fh.getvalue().decode('UTF-8')
  txt_parts = txt.split('\r\n\r\n')
  print(F'File "{f_name}" with {len(txt)} characters has {len(txt_parts)} paragraphs.')
  for j in range(0, len(txt_parts)): # j = 3
    txt_part = txt_parts[j].strip()
    if len(txt_part) < 10:
      continue
    tags = get_txt_tags(txt_part, txt_tags, f_name, doc_tags_json)
    print(tags)

# remove last comma from doc_tags_json, add closing bracket "]"
with open(doc_tags_json, 'rb+') as f:
  f.seek(-10, os.SEEK_END)
  f.truncate()
  f.write("\n]".encode('UTF-8'))
