# read all Google Docs in the folder "ba" and apply tags to them
# output: doc_tags.json
#
# install Google Python modules:
# pip3.10 install --upgrade \
#   python-dotenv \
#   google-auth \
#   google-api-python-client \
#   google-auth-httplib2 \
#   google-auth-oauthlib \
#   openai \
#   tiktoken

import os
from datetime import datetime
import openai
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import io
from googleapiclient.http import MediaIoBaseDownload
import re
import tiktoken
import json

# paths and variables
tags_txt         = 'data/tags.txt'
gdrive_dir_query = "name = 'ba' and mimeType = 'application/vnd.google-apps.folder'"
doc_tags_json    = 'data/docs_excerpts_tags.json'
mdl = {
  'id'        : 'gpt-4',
  #'id'        : 'gpt-3.5-turbo',  # ideally 'gpt-4', but not available yet
  'encoding'  : 'gpt-3.5-turbo',  # ideally 'gpt-4', but not available yet
  'max_tokens':  8192,
  'max_chunk_nchar': round(8192/3) }
  # 'max_tokens':  4097,
  # 'max_chunk_nchar': round(4097/3) }

# read tags from tags_txt
with open(tags_txt, 'r') as f:
  tags = f.read().strip('\n')

# load OPENAI_API_KEY from .env
load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')
enc = tiktoken.encoding_for_model(mdl['encoding'])

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
dir_id = drive.files().list(
   q = gdrive_dir_query
   ).execute().get('files', [])[0].get('id')
results = drive.files().list(
   q = "mimeType = 'application/vnd.google-apps.document' and" +
   "'" + dir_id + "' in parents", 
   pageSize=100, fields="nextPageToken, files(id, name)").execute()
documents = results.get('files', [])
# DEBUG: subset to first 3 documents
# documents = documents[0:3]
print(f'Processing {len(documents)} documents')

def get_doc_text(doc):
  id   = doc.get('id')
  name = doc.get('name')
  print(F'Document "{name}" with id "{id}"')
  req = drive.files().export_media(
    fileId   = id,
    mimeType = 'text/plain')
  fh = io.BytesIO()
  downloader = MediaIoBaseDownload(fh, req)
  done = False
  while done is False:
    status, done = downloader.next_chunk()
  text = fh.getvalue().decode('UTF-8')
  return { 
    'id'  : id, 
    'name': name, 
    'text': text}

def get_gpt_chat_response(messages):
  # convert list of dictionaries to a string
  messages_str = json.dumps(messages)
  messages_tokens = len(enc.encode(messages_str))
  response_tokens = mdl['max_tokens'] - messages_tokens
  
  while True:
    try:
      print(f"    begin GPT request ~ {datetime.now()}")
      response = openai.ChatCompletion.create(
        model       = mdl['id'],
        messages    = messages,
        max_tokens  = response_tokens,
        n           = 1,
        temperature = 0.7)
      print(f"    end GPT request ~ {datetime.now()}")
      return response.choices[0].message.content.strip()
    except openai.error.RateLimitError as e:
      print(f"Rate limit error encountered: {e}. Retrying in 1 hour...")
      time.sleep(3600)  # Sleep for 1 hour

def get_doc_chunks(doc, max_chunk_nchar = 12000):
  txt = doc['text']
  # if text is short enough, return it as a single chunk
  if len(txt) < max_chunk_nchar:
    doc['chunks'] = [txt]
    return doc
  # otherwise iterate over lines and clump them into chunks
  # see split_into_many() in https://platform.openai.com/docs/tutorials/web-qa-embeddings
  # split text into lines with at least one non-whitespace character
  lines       = [ln.strip() for ln in txt.split('\n') if len(ln.strip()) > 0]
  lines_nchar = [len(ln) for ln in lines]
  nchar_so_far = 0
  chunk = []
  chunks = []
  # Loop through the lines and lengths joined together in a tuple
  for ln, ln_nchar in zip(lines, lines_nchar):
    # If the number of characters so far plus the number of characters in the current sentence is greater 
    # than the max number of characters, then add the chunk to the list of chunks and reset
    # the chunk and characters so far
    if nchar_so_far + ln_nchar > max_chunk_nchar:
      chunks.append("\n".join(chunk) + "\n")
      chunk = []
      nchar_so_far = 0
    # If the number of characters in the current sentence is greater than the max number of 
    # characters, go to the next sentence
    if ln_nchar > max_chunk_nchar:
      raise Exception(f"Sorry, single lines cannot be longer than {max_chunk_nchar} characters")
    # Otherwise, add the sentence to the chunk and add the number of characters to the total
    chunk.append(ln)
    nchar_so_far += ln_nchar + 1
  doc['chunks'] = chunks
  return doc

def parse_documents_and_tags(documents, tags):
  parsed_data = {}
  initial_message = {
    'role': 'system',
    'content': f"""
      Extract a sequence of plain text excerpts (ignore non-ASCII characters) for a 
      chunks of text comprised of sentences to a full paragraph of related text from documents about environmental impacts around deploying 
      marine renewable energy devices and judiciously suggest the most applicable set of tags from the following list:
      \n
      {tags}.
      \n
      Please provide a sequence (seperated by the pipe character '|') of excerpt and tags in the following format: 
      'EXCERPT: [excerpt 1 text]\n\nTAGS: [tag1, tag2, ...]\n|\nEXCERPT: [excerpt 2 text]\n\nTAGS: [tag1, tag2, ...]\n\n\n\n'"""}
  for i, doc in enumerate(documents): # doc = documents[0]
    doc = get_doc_text(doc)   # add text to doc
    doc = get_doc_chunks(doc, max_chunk_nchar = mdl['max_chunk_nchar']) # add chunks to doc
    print(f"Document {i} '{doc['name']}' n_chunks: {len(doc['chunks'])}")
    for j, chunk in enumerate(doc['chunks']):
      doc_tags_ij_json = f'data/doc_tags_i{i}_j{j}.json'
      if os.path.exists(doc_tags_ij_json):
        print(f"  chunk {j} already processed")
        # read the json file
        with open(doc_tags_ij_json, 'r') as f:
          parsed_data = json.load(f)
        continue
      user_message = {
        'role'   : 'user',
        'content': f"Analyze this chunk of text from a document:\n{chunk}"
      }
      messages = [initial_message, user_message]
      response = get_gpt_chat_response(messages)
      excerpts = response.split('|')
      print(f"  chunk {j} len(excerpts): {len(excerpts)}")
      # if i == 0 and j == 3:
      #   print('DEBUG: excerpts[0]:', excerpts[0])
      def excerpt_to_text_tags(excerpt): # excerpt = excerpts[0]
        print('\n\n', excerpt, '\n\n')
        #excerpt = "EXCERPT: Is there other Federal government involvement outside of EERE in any aspect of this project (e.g., funding, permitting, technical assistance, project located on Federally administered land)? Yes:  "
        if excerpt.count('EXCERPT: ') == 1 & excerpt.count('TAGS: ') == 1:
          text = excerpt.split('EXCERPT: ')[1].split('TAGS: ')[0].strip()
          tags = excerpt.split('TAGS: ')[1].strip().split(', ')
          return {
            'text': text, 
            'tags': tags}
        elif excerpt.count('EXCERPT: ') == 1 & excerpt.count('TAGS: ') != 1:
          return {
            'text': excerpt.split('EXCERPT: ')[1], 
            'tags': None}
        else:
          return {
            'text': excerpt, 
            'tags': None}
      chunk_excerpts = [excerpt_to_text_tags(excerpt) for excerpt in excerpts]
      if doc['name'] in parsed_data.keys():
        parsed_data[doc['name']] += chunk_excerpts
      else:
        parsed_data[doc['name']] = chunk_excerpts
      with open(doc_tags_ij_json, 'w') as f:
        f.write(json.dumps(parsed_data, indent=2))
  return parsed_data

parsed_data = parse_documents_and_tags(documents, tags)
with open(doc_tags_json, 'w') as f:
  f.write(json.dumps(parsed_data, indent=2))
