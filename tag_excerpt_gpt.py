# read input argument of an excerpt and return the tags
# 
#   python tag_excerpt_gpt.py "{excerpt_txt}" "{mdl_version}"
#
# where:
#   excerpt_txt: path to file with text to tag, should be wrapped in double quotes and have them replaced internally with single quotes
#   mdl_version: so far either "3" or "4"
#
# try in Terminal:
#   python /share/github/ba/tag_excerpt_gpt.py "Do not approach within 100 feet of whales. If whales approach within 100 feet of your vessel, put engines in neutral and do not re-engage propulsion until whales are observed clear of harm's way from your vessel." "4"
#
# install Google Python modules as Shiny on rstudio.marineenergy.app
# sudo su - shiny
# pip install --user --upgrade \
#   pandas \
#   python-dotenv \
#   google-auth \
#   google-api-python-client \
#   google-auth-httplib2 \
#   google-auth-oauthlib \
#   openai \
#   tiktoken

import sys
from pathlib import Path
import os
from datetime import datetime
import time
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
import pandas as pd

excerpt_txt = sys.argv[1]
with open(excerpt_txt, 'r') as f:
  excerpt = f.read().strip('\n')

if len(sys.argv) > 2:
  mdl_version = sys.argv[2]
else:
  mdl_version = '3.5'
  
# DEBUG
# excerpt = """
# Do not approach within 100 feet of whales. If whales approach within 100 feet of 
# your vessel, put engines in neutral and do not re-engage propulsion until whales 
# are observed clear of harm's way from your vessel.
# """
# excerpt = "Do not approach within 100 feet of whales. If whales approach within 100 feet of your vessel, put engines in neutral and do not re-engage propulsion until whales are observed clear of harm's way from your vessel."
# GPT-3 (temp=0): Receptor.MarineMammals, Consequence.Injury, Stressor.PhysicalInteraction
# GPT-4 (temp=0): Receptor.MarineMammals.Cetaceans, Management.Mitigation, Consequence.Collision
# GPT-4 (temp=0): Consequence.BehavioralChange, Management.Mitigation, Receptor.MarineMammals.Cetaceans, Stressor.BehavioralInteraction.Avoidance
# GPT-4 (temp=0): Receptor.MarineMammals.Cetaceans, Management.Mitigation, Consequence.Collision

# paths and variables
script_dir = Path( __file__ ).parent.absolute()
# script_dir = "/share/github/ba"
tags_csv = f'{script_dir}/../apps_dev/data/tags.csv'

# GPT models
mdls = {
  '3.5': {
    'id'             : 'gpt-3.5-turbo',
    'encoding'       : 'gpt-3.5-turbo',
    'temperature'    : 0,
    'max_tokens'     :  4097,
    'max_chunk_nchar': round(4097/3) },
  '4': {
    'id'             : 'gpt-4o',
    'encoding'       : 'gpt-4',
    'temperature'    : 0,
    'max_tokens'     : 4097,
    'max_chunk_nchar': round(4097/3) } }
mdl = mdls[mdl_version]

# read tags from tags_csv
df = pd.read_csv(tags_csv, usecols = ['tag_sql'])
tags = df.to_string(header=False, index=False)
# print(tags)

# load OPENAI_API_KEY from .env
load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')
enc = tiktoken.encoding_for_model(mdl['encoding'])

def get_gpt_chat_response(messages):
  messages_str    = json.dumps(messages)
  messages_tokens = len(enc.encode(messages_str))
  response_tokens = mdl['max_tokens'] - messages_tokens
  try:
    response = openai.ChatCompletion.create(
      model       = mdl['id'],
      messages    = messages,
      max_tokens  = response_tokens,
      n           = 1,
      temperature = mdl['temperature']) # zero randomness
    return response.choices[0].message.content.strip()
  except Exception as e:
    return f"Error with ChatGPT request: {e}"

initial_message = {
  'role': 'system',
  'content': f"""
    Your task is to judiciously apply a small subset of tags to an excerpt from 
    a document about environmental impacts around deploying marine renewable 
    energy devices. Here is the full set of tags:
    \n
    {tags}.
    \n
    Please provide a comma-seperated sequence tags after I give you the excerpt."""}
user_message = {
  'role'   : 'user',
  'content': f"""
    Analyze this excerpt for the minimal set of applicable tags:
    \n
    {excerpt}
    """
}
messages = [initial_message, user_message]
response = get_gpt_chat_response(messages)
print(response)
