console.log("DEBUG: src/App.jsx module execution started.");
import { useState, useEffect, useCallback } from "react";
import "./App.css";
import { init as initZstd, decompress } from "@bokuweb/zstd-wasm";
import { Buffer } from "buffer";
import JSZip from "jszip";
import initSqlJs from "sql.js";
import { Model } from "./utils/genanki/model";
import { Deck } from "./utils/genanki/deck";
import { Package } from "./utils/genanki/package";

// Helper to extract filename from URL (JavaScript version)
const extractFilenameFromUrl = (url) => {
  try {
    const parsedUrl = new URL(url);
    return parsedUrl.pathname.split("/").pop();
  } catch {
    // Fallback for non-standard URLs or if URL parsing fails
    const parts = url.split("/");
    return parts[parts.length - 1];
  }
};

// Default Model and Deck IDs (generate randomly or use stable ones)
const DEFAULT_MODEL_ID = () =>
  Math.floor(Math.random() * (2 ** 31 - 1)) + 2 ** 30;
const DEFAULT_DECK_ID = () =>
  Math.floor(Math.random() * (2 ** 31 - 1)) + 2 ** 30;

function App() {
  const [ofcFile, setOfcFile] = useState(null);
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState("");
  const [error, setError] = useState(null);
  const [isConverting, setIsConverting] = useState(false);
  const [sqlJs, setSqlJs] = useState(null);

  // Initialize ZSTD and SQL.js
  useEffect(() => {
    const initialize = async () => {
      try {
        // Quieter logs
        console.log("Initializing libraries...");
        await initZstd();
        const SQL = await initSqlJs({
          locateFile: (file) => `https://sql.js.org/dist/${file}`,
        });
        setSqlJs(SQL);
        console.log("Libraries initialized.");
      } catch (err) {
        console.error("Initialization error:", err);
        setError("Failed to initialize necessary libraries. " + err.message);
      }
    };
    initialize();
  }, []);

  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file && file.name.endsWith(".ofc")) {
      setOfcFile(file);
      setError(null);
      setProgress(0);
      setProgressMessage("");
    } else {
      setOfcFile(null);
      setError("Please select a valid .ofc file.");
    }
  };

  const convertOFCtoAPKG = useCallback(async () => {
    if (!ofcFile) {
      setError("No .ofc file selected.");
      return;
    }
    if (!sqlJs) {
      setError("SQL.js not initialized yet. Please wait.");
      return;
    }

    setIsConverting(true);
    setError(null);
    setProgress(0);

    try {
      const ankiModel = new Model({
        id: DEFAULT_MODEL_ID(),
        name: "AnkiPro Imported Model",
        flds: [{ name: "Front" }, { name: "Back" }],
        tmpls: [
          {
            name: "Card 1",
            qfmt: "{{Front}}",
            afmt: "{{FrontSide}}\n\n<hr id=answer>\n\n{{Back}}",
          },
        ],
        req: [
          // Basic requirement: first field for first card, second for second (if reversed)
          [0, "all", [0]],
        ],
        // Add other model properties like css if needed
      });

      setProgress(5);
      setProgressMessage("Reading .ofc file...");
      const fileBuffer = await ofcFile.arrayBuffer();

      setProgress(10);
      setProgressMessage("Unzipping .ofc file...");
      const zip = await JSZip.loadAsync(fileBuffer);

      const metadataFile = zip.file("deck_export_metadata.json");
      if (!metadataFile)
        throw new Error("deck_export_metadata.json not found in .ofc file.");
      const metadataContent = await metadataFile.async("string");
      const metadata = JSON.parse(metadataContent);
      const deckName = metadata.deck_name || "Imported AnkiPro Deck";
      setProgressMessage(`Processing deck: ${deckName}`);

      const deckDataFile = zip.file("deck_export_data");
      if (!deckDataFile)
        throw new Error("deck_export_data not found in .ofc file.");
      const compressedData = await deckDataFile.async("uint8array");

      setProgress(20);
      setProgressMessage("Decompressing deck data (zstd)...");
      const decompressedData = decompress(compressedData);
      const deckDataJson = Buffer.from(decompressedData).toString("utf-8");
      const ankiproDecksData = JSON.parse(deckDataJson);

      const ankiPackage = new Package(sqlJs); // Use the initialized SQL.js
      const allMediaFiles = {}; // To store { "filename.png": ArrayBuffer }

      let currentNote = 0;
      const totalNotesToProcess = ankiproDecksData.reduce(
        (sum, deck) => sum + (deck.notes ? deck.notes.length : 0),
        0
      );
      let mediaDownloadsCount = 0;
      const totalMediaAttachments = ankiproDecksData.reduce(
        (sum, deck) =>
          sum +
          deck.notes.reduce(
            (noteSum, note) =>
              noteSum +
              (note.note_attachments ? note.note_attachments.length : 0),
            0
          ),
        0
      );

      for (const apDeckData of ankiproDecksData) {
        const currentDeckId = apDeckData.anki_deck_id || DEFAULT_DECK_ID();
        const currentDeckName = apDeckData.name || deckName;
        const ankiDeck = new Deck(currentDeckId, currentDeckName);

        const notesData = apDeckData.notes || [];
        for (const noteData of notesData) {
          currentNote++;
          setProgress(
            20 + Math.floor(30 * (currentNote / (totalNotesToProcess || 1))) // Avoid division by zero
          );
          setProgressMessage(
            `Processing note ${currentNote}/${totalNotesToProcess}...`
          );

          let frontContent = noteData.fields?.front_side || "";
          let backContent = noteData.fields?.back_side || "";

          const noteAttachments = noteData.note_attachments || [];
          for (const attachmentInfo of noteAttachments) {
            const mediaDetails = attachmentInfo.attachment;
            if (
              mediaDetails &&
              mediaDetails.media_file &&
              mediaDetails.media_file.url
            ) {
              const mediaUrl = mediaDetails.media_file.url;
              const imgFilename = extractFilenameFromUrl(mediaUrl);

              setProgressMessage(`Downloading media: ${imgFilename}...`);
              try {
                const response = await fetch(mediaUrl);
                if (!response.ok) {
                  console.warn(
                    `Failed to download media ${imgFilename}: ${response.statusText}`
                  );
                  continue;
                }
                const mediaData = await response.arrayBuffer();
                allMediaFiles[imgFilename] = mediaData;
                mediaDownloadsCount++;
                if (totalMediaAttachments > 0) {
                  // Avoid division by zero
                  setProgress(
                    50 +
                      Math.floor(
                        30 * (mediaDownloadsCount / totalMediaAttachments)
                      )
                  );
                }

                const imgTag = `<img src="${imgFilename}">`;
                const fieldToAppend = attachmentInfo.field_name || "back_side";
                if (fieldToAppend === "front_side") {
                  frontContent += `<br>${imgTag}`;
                } else {
                  backContent += `<br>${imgTag}`;
                }
              } catch (e) {
                console.warn(`Error downloading media ${imgFilename}:`, e);
              }
            }
          }

          const ankiNote = ankiModel.note(
            [frontContent, backContent],
            null,
            noteData.id ? String(noteData.id) : undefined
          );
          ankiDeck.addNote(ankiNote);
        }
        ankiPackage.addDeck(ankiDeck);
      }

      setProgress(80);
      setProgressMessage("Adding media files to package...");

      // Correctly add media files to the package
      for (const [fileName, fileData] of Object.entries(allMediaFiles)) {
        ankiPackage.addMedia(fileData, fileName); // Use the addMedia method
      }

      setProgress(90);
      setProgressMessage("Generating .apkg file...");

      const outputFileName =
        ofcFile.name.replace(/\.ofc$/, ".apkg") || "converted_deck.apkg";

      await ankiPackage.writeToFile(outputFileName);

      setProgress(100);
      setProgressMessage("Conversion complete! Download should have started.");
    } catch (err) {
      console.error("Conversion failed:", err);
      setError(`Conversion failed: ${err.message}`);
      setProgress(0);
    } finally {
      setIsConverting(false);
    }
  }, [ofcFile, sqlJs]);

  return (
    <>
      <h1>OFC to APKG Converter (Client-Side)</h1>
      <div className="card">
        <input
          type="file"
          accept=".ofc"
          onChange={handleFileChange}
          disabled={isConverting}
        />
        <button
          onClick={convertOFCtoAPKG}
          disabled={!ofcFile || isConverting || !sqlJs}
        >
          {isConverting ? "Converting..." : "Convert to .apkg"}
        </button>
        {isConverting && (
          <div>
            <progress value={progress} max="100"></progress>
            <p>
              {progress}% - {progressMessage}
            </p>
          </div>
        )}
        {error && (
          <div className="message-container error-message">
            <p>Error: {error}</p>
          </div>
        )}
        {!isConverting && progress === 100 && (
          <div className="message-container success-message">
            <p>{progressMessage}</p>
          </div>
        )}
      </div>
      <p className="read-the-docs">
        Upload an .ofc file. The conversion happens in your browser. Nothing is
        uploaded to the server.
      </p>
    </>
  );
}

export default App;
