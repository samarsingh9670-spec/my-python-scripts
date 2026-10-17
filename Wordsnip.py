import time
import win32com.client
import win32clipboard
from PIL import ImageGrab

def clipboard_has_image():
    win32clipboard.OpenClipboard()
    try:
        return win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_DIB)
    finally:
        win32clipboard.CloseClipboard()

def get_clipboard_image_bytes():
    img = ImageGrab.grabclipboard()
    if img:
        return img.tobytes()
    return None

last_image_bytes = None

print("✅ Snip-to-Word is running. Press Ctrl+C to stop.")

while True:
    try:
        if clipboard_has_image():
            img_bytes = get_clipboard_image_bytes()

            # Only act on a NEW snip
            if img_bytes and img_bytes != last_image_bytes:
                last_image_bytes = img_bytes

                # Connect to already-open Word
                word = win32com.client.GetActiveObject("Word.Application")

                # Paste at current cursor location
                word.Selection.Paste()
                time.sleep(0.2)

                # Resize pasted image
                shape = word.Selection.InlineShapes(1)
                shape.LockAspectRatio = True
                shape.Width = word.CentimetersToPoints(14)

                # Move cursor below image
                word.Selection.TypeParagraph()

        time.sleep(0.3)

    except KeyboardInterrupt:
        print("🛑 Stopped.")
        break
    except Exception:
        # Ignore transient clipboard/COM timing errors
        time.sleep(0.3)