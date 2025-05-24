import zipfile
import zstandard
import json
import os
import shutil
import random
import genanki
import tempfile
import argparse
from urllib.parse import urlparse
import requests  # Added for downloading media

# --- genanki Model and Deck IDs ---
# It's important to use unique IDs. Generate them once and hardcode them.
# python -c "import random; print(random.randrange(1 << 30, 1 << 31))"
DEFAULT_MODEL_ID = random.randrange(1 << 30, 1 << 31)
DEFAULT_DECK_ID = random.randrange(1 << 30, 1 << 31)

# Define a User-Agent header
REQUEST_HEADERS = {
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
}

ANKI_MODEL = genanki.Model(
    DEFAULT_MODEL_ID,
    "AnkiPro Imported Model",
    fields=[
        {"name": "Front"},
        {"name": "Back"},
    ],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        },
    ],
)


def generate_guid(note_data):
    """
    Generates a GUID for a note.
    The default genanki GUID is a hash of all fields.
    We can customize this if needed, e.g., based on the AnkiPro note ID.
    """
    # For now, let genanki handle it, but we can use note_data['id']
    # return genanki.guid_for(str(note_data.get('id', random.random())))
    # return None # Let genanki auto-generate based on fields
    note_id = note_data.get("id")
    if note_id is not None:
        return genanki.guid_for(str(note_id))
    return None  # Fallback to genanki default if no ID


def extract_filename_from_url(url):
    """Extracts the filename from a URL."""
    parsed_url = urlparse(url)
    return os.path.basename(parsed_url.path)


def download_media(url, download_path):
    """Downloads a file from a URL to a given path."""
    try:
        response = requests.get(url, stream=True, headers=REQUEST_HEADERS)
        response.raise_for_status()  # Raise an exception for HTTP errors
        with open(download_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Successfully downloaded {os.path.basename(download_path)} from {url}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error downloading {url}: {e}")
        return False


def process_ofc_file(ofc_path, output_apkg_path):
    """
    Converts an AnkiPro .ofc file (or directory) to an Anki .apkg file.
    """
    is_dir = os.path.isdir(ofc_path)
    temp_dir = None

    if is_dir:
        base_path = ofc_path
    else:
        if not ofc_path.lower().endswith(".ofc"):
            print(f"Error: Input file '{ofc_path}' is not an .ofc file.")
            return
        temp_dir = tempfile.mkdtemp(prefix="ankipro_import_")
        try:
            # Unzip the .ofc file itself to get deck_export_data and deck_export_metadata.json
            with zipfile.ZipFile(ofc_path, "r") as zip_ref:
                # Selectively extract necessary files if possible, or extract all
                # For simplicity, extract all to temp_dir, which becomes base_path
                zip_ref.extractall(temp_dir)
            base_path = temp_dir
        except zipfile.BadZipFile:
            print(f"Error: Could not unzip '{ofc_path}'.")
            if temp_dir:
                shutil.rmtree(temp_dir)
            return
        except Exception as e:
            print(f"Error during unzipping: {e}")
            if temp_dir:
                shutil.rmtree(temp_dir)
            return

    print(f"Processing content from: {base_path}")

    deck_metadata_path = os.path.join(base_path, "deck_export_metadata.json")
    deck_data_path = os.path.join(base_path, "deck_export_data")
    # attachments_zip_path = os.path.join(base_path, "attachments.zip") # No longer used
    attachments_dir = os.path.join(base_path, "attachments")

    media_files_paths = []
    # media_files_for_anki = [] # No longer strictly needed for pre-check, but useful for collecting basenames

    # Create attachments_dir if it doesn't exist, for downloaded media
    if not os.path.isdir(attachments_dir):
        os.makedirs(attachments_dir, exist_ok=True)
        print(f"Created attachments directory at {attachments_dir} for downloads")

    # Logic for extracting attachments.zip and scanning local attachments_dir is removed.

    if not os.path.exists(deck_metadata_path):
        print(f"Error: deck_export_metadata.json not found in {base_path}")
        if temp_dir:
            shutil.rmtree(temp_dir)
        return
    with open(deck_metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    deck_name = metadata.get("deck_name", "Imported AnkiPro Deck")
    print(f"Deck name: {deck_name}")

    if not os.path.exists(deck_data_path):
        print(f"Error: deck_export_data not found in {base_path}")
        if temp_dir:
            shutil.rmtree(temp_dir)
        return
    with open(deck_data_path, "rb") as f:
        compressed_data = f.read()
    dctx = zstandard.ZstdDecompressor()
    try:
        decompressed_data = dctx.decompress(compressed_data)
        ankipro_decks_data = json.loads(decompressed_data.decode("utf-8"))
    except Exception as e:  # Catching generic ZstdError or JSONDecodeError
        print(f"Error processing deck_export_data: {e}")
        if temp_dir:
            shutil.rmtree(temp_dir)
        return

    anki_decks = []
    for ap_deck_data in ankipro_decks_data:
        current_deck_id = (
            ap_deck_data.get("anki_deck_id") or DEFAULT_DECK_ID
        )  # Try to get from data
        if (
            current_deck_id == DEFAULT_DECK_ID
        ):  # If still default, use a new random one for this specific deck
            current_deck_id = random.randrange(1 << 30, 1 << 31)

        current_deck_name = ap_deck_data.get("name") or deck_name

        anki_deck = genanki.Deck(current_deck_id, current_deck_name)
        notes_data = ap_deck_data.get("notes", [])

        for note_data in notes_data:
            fields = note_data.get("fields", {})
            front_content = fields.get("front_side", "")
            back_content = fields.get("back_side", "")

            note_media_attachments = note_data.get("note_attachments", [])
            for attachment_info in note_media_attachments:
                media_details = attachment_info.get("attachment")
                if media_details:
                    media_url = media_details.get("media_file", {}).get("url")
                    if media_url:
                        img_filename = extract_filename_from_url(media_url)
                        local_img_path = os.path.join(attachments_dir, img_filename)

                        # Always attempt to download. If it fails, it will be skipped.
                        print(
                            f"Attempting to download media '{img_filename}' from {media_url}..."
                        )
                        if download_media(media_url, local_img_path):
                            if local_img_path not in media_files_paths:
                                media_files_paths.append(local_img_path)
                            # img_filename will be used in img_tag
                            img_tag = f'<img src="{img_filename}">'
                            field_to_append = attachment_info.get(
                                "field_name", "back_side"
                            )
                            if field_to_append == "front_side":
                                front_content += f"<br>{img_tag}"
                            else:  # Includes back_side and any other/default
                                back_content += f"<br>{img_tag}"
                        else:
                            print(
                                f"Warning: Failed to download {img_filename}. It will be missing."
                            )

            anki_note = genanki.Note(
                model=ANKI_MODEL,
                fields=[front_content, back_content],
                guid=generate_guid(note_data),
            )
            anki_deck.add_note(anki_note)
        anki_decks.append(anki_deck)

    if not anki_decks:
        print("No decks were processed.")
        if temp_dir:
            shutil.rmtree(temp_dir)
        return

    if len(anki_decks) > 1:
        print(f"Packaging {len(anki_decks)} decks into '{output_apkg_path}'.")
        anki_package = genanki.Package(anki_decks)
    elif anki_decks:
        anki_package = genanki.Package(anki_decks[0])
    else:
        if temp_dir:
            shutil.rmtree(temp_dir)
        return

    unique_media_paths = sorted(list(set(media_files_paths)))
    print(f"Total unique media files to include: {len(unique_media_paths)}")
    # for p in unique_media_paths:
    #     print(f"  - {p} (basename: {os.path.basename(p)})") # Potentially verbose

    anki_package.media_files = unique_media_paths

    try:
        anki_package.write_to_file(output_apkg_path)
        print(f"Successfully created Anki package: {output_apkg_path}")
    except Exception as e:
        print(f"Error writing .apkg file: {e}")

    if temp_dir:
        print(f"Cleaning up temporary directory: {temp_dir}")
        shutil.rmtree(temp_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Convert AnkiPro .ofc files to Anki .apkg files."
    )
    parser.add_argument(
        "input_path", help="Path to the .ofc file or the unzipped .ofc directory."
    )
    parser.add_argument(
        "output_path",
        help="Path to save the generated .apkg file (e.g., my_deck.apkg).",
    )

    args = parser.parse_args()

    # Validate output path
    if not args.output_path.lower().endswith(".apkg"):
        print(
            "Warning: Output path does not end with .apkg. It will be saved as specified."
        )
        # You might want to enforce .apkg or automatically append it.
        # args.output_path += ".apkg" # Example: auto-append

    if not os.path.exists(args.input_path):
        print(f"Error: Input path '{args.input_path}' does not exist.")
        return

    process_ofc_file(args.input_path, args.output_path)


if __name__ == "__main__":
    # Example Usage (for testing in an IDE without CLI args):
    process_ofc_file(
        "mass_spectrometry_2025_05_23_204000.ofc",
        "mass_spectrometry_2025_05_23_204000.apkg",
    )
