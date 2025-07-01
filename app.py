import streamlit as st
import google.generativeai as genai
import requests
import time
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from google.api_core.exceptions import ResourceExhausted
import json

# ====== LOAD CONFIGS FROM SECRETS ======
GENAI_API_KEY = st.secrets["api"]["gemini_key"]
SPREADSHEET_ID = st.secrets["sheets"]["spreadsheet_id"]
SERVICE_ACCOUNT_INFO = dict(st.secrets["google_service_account"])


genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

PROMPT = """
This is a screenshot of a chat or message from a social media or messaging platform. 
Please extract the following details from the image:
Client Name, Mobile No., Center, Source.

- "Source" should be the platform/app detected from the screenshot (e.g. WhatsApp, Telegram, Twitter, Instagram, Facebook, etc).
- Return ONLY a single CSV row (no header), values in this order, comma separated.
Example:
Karan Patel,+918954687354,Jagatpura,WhatsApp
"""


# ========== HELPER FUNCTIONS ==========
def get_direct_download_link(link):
    if "drive.google.com" in link:
        if "id=" in link:
            file_id = link.split("id=")[-1].split("&")[0]
        elif "/d/" in link:
            file_id = link.split("/d/")[1].split("/")[0]
        else:
            return None
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return link


def download_image_bytes(image_url):
    try:
        response = requests.get(image_url)
        if response.status_code == 200 and "image" in response.headers.get(
            "Content-Type", ""
        ):
            return response.content
        return None
    except:
        return None


def call_gemini(image_bytes):
    image_input = {
        "mime_type": "image/jpeg",
        "data": image_bytes,
    }

    for attempt in range(5):
        try:
            response = model.generate_content(
                [{"role": "user", "parts": [PROMPT, image_input]}]
            )
            return response.text.strip(), None
        except ResourceExhausted:
            time.sleep(60)
    return None, "Gemini quota exhausted."


def append_to_sheet(csv_row, original_link):
    values = [original_link] + [x.strip() for x in csv_row.split(",")]
    if len(values) != 5:
        return False, "Unexpected output format."

    credentials = Credentials.from_service_account_info(
        SERVICE_ACCOUNT_INFO, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    service = build("sheets", "v4", credentials=credentials)
    sheet = service.spreadsheets()

    request = sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range="Sheet1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [values]},
    )
    request.execute()
    return True, None


# ========== STREAMLIT UI ==========
st.set_page_config(page_title="📷 Image to Sheet", layout="wide")
st.title("📥 Extract Chat Info from Screenshot & Save to Google Sheet")

raw_link = st.text_input("Paste public image URL (Direct Image Link):")

if raw_link:
    image_url = get_direct_download_link(raw_link)
    image_bytes = download_image_bytes(image_url)

    if not image_bytes:
        st.error("❌ Could not fetch a valid image from the link.")
    else:
        st.image(image_url, caption="Detected Image", width=350)

        with st.spinner("Processing image..."):
            result, error = call_gemini(image_bytes)

        if error:
            st.error(error)
        elif result:
            st.success("✅ Output:")
            st.code(result, language="csv")

            success, sheet_error = append_to_sheet(result, raw_link)
            if success:
                st.success("✅ Data appended to Google Sheet.")
            else:
                st.error(f"❌ Sheet Error: {sheet_error}")
