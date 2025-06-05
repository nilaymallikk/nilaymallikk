import os
import json
import re
import base64
import io
import zipfile
from flask import Flask, request, jsonify, send_file

# Initialize Flask app
app = Flask(__name__)

# Load and configure Google API Key
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
gemini_api_configured = False
imagen_client = None

if not GOOGLE_API_KEY:
    print("FATAL ERROR: GOOGLE_API_KEY environment variable not set.")
else:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        print("Google API Key configured successfully for Gemini (genai.configure).")
        gemini_api_configured = True

        try:
            imagen_client = genai.Client(api_key=GOOGLE_API_KEY)
            print("genai.Client for Imagen initialized successfully.")
        except AttributeError:
            print("WARNING: `genai.Client` not found. Image generation will use placeholders or fail if attempted.")
            imagen_client = None
        except Exception as e:
            print(f"ERROR: Failed to initialize genai.Client for Imagen: {e}")
            imagen_client = None

    except Exception as e:
        print(f"FATAL ERROR: Failed to configure Google API Key with genai.configure: {e}")

def extract_json_from_markdown(md_string):
    if md_string is None: return None
    match = re.search(r"```json\s*([\s\S]*?)\s*```", md_string)
    if match: return match.group(1)
    try:
        json.loads(md_string)
        return md_string
    except json.JSONDecodeError:
        print(f"Warning: Could not extract JSON from string: {md_string[:100]}...")
    return None

@app.route('/generate', methods=['POST'])
def generate_slides():
    if not gemini_api_configured:
        return jsonify({"error": "Server configuration error: Gemini API key not properly configured."}), 500

    data = request.get_json()
    topic = data.get('topic')
    if not topic: return jsonify({"error": "No topic provided"}), 400

    system_prompt = f"""You are explaining the topic: "{topic}".

Use a fun story about Miko the monkey and bananas as a metaphor. Miko is an adorable monkey, and bananas should always be yellow.

Break the explanation into short, conversational, casual, and engaging sentences.

For each sentence, also create a concise prompt for an image generation model. This prompt should describe a cute, minimal illustration for that sentence, featuring Miko the monkey and yellow bananas, in black ink on a white background, suitable for a slideshow.

Respond with a JSON array of objects, where each object has two keys: "sentence" (string) and "imagePrompt" (string).

Ensure the JSON is well-formed and the array is not empty. Ensure there are at least 10 objects in the array.

No commentary outside the JSON. Just provide the JSON array.

Example of a single element in the array:

{{ "sentence": "Miko the monkey shows how data packets (represented by yellow bananas) scurry through network cables.", "imagePrompt": "Miko the monkey pointing at yellow bananas scurrying through abstract network cables, black ink, white background, minimal style." }}

Keep going until the explanation is complete and you have at least 10 sentence/imagePrompt pairs.
"""
    parsed_slides_data = []
    raw_text_output = "Error: AI response not captured" # Default error message
    gemini_response_obj = None # Initialize to avoid reference before assignment in case of early error

    try:
        print(f"Generating text content for topic: {topic}")
        text_model = genai.GenerativeModel('gemini-1.5-flash-latest')
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        gemini_response_obj = text_model.generate_content(system_prompt, safety_settings=safety_settings)
        raw_text_output = gemini_response_obj.text
        json_string = extract_json_from_markdown(raw_text_output)

        if not json_string:
            print(f"Error: Could not extract JSON from Gemini response. Response text: {raw_text_output}")
            return jsonify({"error": "Failed to parse text generation response from AI."}), 500

        parsed_slides_data = json.loads(json_string)
        if not isinstance(parsed_slides_data, list) or not all(isinstance(item, dict) and 'sentence' in item and 'imagePrompt' in item for item in parsed_slides_data):
            print(f"Error: Text generation output is not in the expected format. Parsed data: {parsed_slides_data}")
            return jsonify({"error": "Text generation output format error."}), 500
        if not parsed_slides_data:
             print(f"Error: Text generation returned an empty list of slides.")
             return jsonify({"error": "Text generation failed to produce content."}), 500

    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from Gemini: {e}. Response text was: {raw_text_output}")
        return jsonify({"error": "Failed to decode JSON response from AI text generation."}), 500
    except Exception as e:
        if gemini_response_obj and hasattr(gemini_response_obj, 'prompt_feedback') and gemini_response_obj.prompt_feedback.block_reason:
            block_reason = gemini_response_obj.prompt_feedback.block_reason
            safety_ratings_str = ", ".join([f"{rating.category}: {rating.probability}" for rating in gemini_response_obj.prompt_feedback.safety_ratings])
            print(f"Content generation blocked by Gemini due to: {block_reason}. Safety ratings: {safety_ratings_str}")
            return jsonify({"error": f"Content generation blocked by safety filters: {block_reason}. Please revise your topic."}), 400
        print(f"Error during text generation: {e}")
        return jsonify({"error": f"An error occurred during text generation: {str(e)}"}), 500

    slides_with_images = []
    if not imagen_client:
        print("WARNING: Imagen client (`genai.Client`) not available. Using placeholders for images.")
        for i, item in enumerate(parsed_slides_data):
            item['imageUrl'] = f'https://via.placeholder.com/600x400.png?text=Imagen+Client+Error+{i+1}'
            slides_with_images.append(item)
    else:
        print(f"Starting image generation for {len(parsed_slides_data)} slides.")
        for i, item in enumerate(parsed_slides_data):
            image_generation_prompt = item.get('imagePrompt', 'Miko the monkey with a yellow banana, black ink, white background, minimal style')
            print(f"Slide {i+1}: Generating image with prompt: '{image_generation_prompt}'")
            try:
                image_response = imagen_client.models.generate_images(
                    model="imagen-3.0-generate-002",
                    prompt=image_generation_prompt,
                    config=dict(number_of_images=1, output_mime_type="image/png", aspect_ratio="16:9")
                )
                if image_response.generated_images and image_response.generated_images[0].image.image_bytes:
                    img_bytes = image_response.generated_images[0].image.image_bytes
                    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                    item['imageUrl'] = f"data:image/png;base64,{img_base64}"
                    print(f"Slide {i+1}: Successfully generated image for prompt: '{image_generation_prompt}'")
                else:
                    item['imageUrl'] = 'placeholder_error_no_image_data.png'
                    print(f"Slide {i+1}: No image data returned for prompt: '{image_generation_prompt}'. Response: {image_response}")
            except Exception as e:
                print(f"Slide {i+1}: ERROR generating image for prompt '{image_generation_prompt}'. Exception: {e}")
                if hasattr(e, 'response') and e.response:
                    print(f"Underlying error response: {e.response.text if hasattr(e.response, 'text') else 'N/A'}")
                item['imageUrl'] = 'placeholder_api_error.png'
            slides_with_images.append(item)

    if not slides_with_images and parsed_slides_data : # If image processing failed for all, but text succeeded
        print("Warning: Image generation failed for all items, returning text-generated data with placeholders.")
        slides_with_images = [] # Re-init to avoid sending partially modified items if logic changes
        for i, item_text_only in enumerate(parsed_slides_data):
            item_text_only['imageUrl'] = f'https://via.placeholder.com/600x400.png?text=Overall+Img+Fail+{i+1}'
            slides_with_images.append(item_text_only)


    elif not slides_with_images and not parsed_slides_data: # Both failed
        print("Error: No slides with images were processed, and text generation also failed or yielded no data.")
        return jsonify({"error": "Failed to process slides for image generation and text generation yielded no data."}), 500

    return jsonify(slides_with_images)

@app.route('/download', methods=['POST'])
def download_slides():
    request_data = request.get_json()
    if not request_data or 'slides' not in request_data:
        return jsonify({"error": "Missing 'slides' data in request."}), 400

    slides = request_data.get('slides')
    if not isinstance(slides, list) or not slides:
        return jsonify({"error": "Invalid or empty 'slides' data."}), 400

    print(f"Preparing ZIP file for {len(slides)} slides.")
    zip_buffer = io.BytesIO()
    all_sentences = []

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_f:
        for i, slide in enumerate(slides):
            sentence = slide.get('sentence', f'Sentence for slide {i+1} not found.')
            all_sentences.append(f"Slide {i+1}:\n{sentence}\n")

            image_url = slide.get('imageUrl', '')
            if image_url.startswith('data:image/png;base64,'):
                base64_string = image_url.replace('data:image/png;base64,', '')
                try:
                    image_bytes = base64.b64decode(base64_string)
                    zip_f.writestr(f'slide_{i+1}.png', image_bytes)
                    print(f"Added slide_{i+1}.png to ZIP.")
                except base64.binascii.Error as e:
                    print(f"Error decoding base64 for slide {i+1}: {e}. Skipping image.")
                    zip_f.writestr(f'slide_{i+1}_decoding_error.txt', f"Could not decode image: {e}")
                except Exception as e:
                    print(f"General error processing image for slide {i+1}: {e}. Skipping image.")
                    zip_f.writestr(f'slide_{i+1}_processing_error.txt', f"Could not process image: {e}")
            elif image_url.startswith('http'): # Placeholder or error image URL
                print(f"Slide {i+1} has a placeholder/error URL: {image_url}. Adding as text.")
                zip_f.writestr(f'slide_{i+1}_image_link.txt', f"Image was a placeholder/link: {image_url}\nAssociated prompt: {slide.get('imagePrompt', 'N/A')}")
            else: # Unknown image format or missing
                print(f"Slide {i+1} has no valid image data. Adding as text.")
                zip_f.writestr(f'slide_{i+1}_no_image.txt', f"No valid image data found for this slide.\nAssociated prompt: {slide.get('imagePrompt', 'N/A')}")

        # Add all sentences to a single text file
        zip_f.writestr('slideshow_text.txt', "\n".join(all_sentences))
        print("Added slideshow_text.txt to ZIP.")

    zip_buffer.seek(0)
    print("ZIP file created successfully. Sending to client.")
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name='monkey_banana_slideshow.zip',
        mimetype='application/zip'
    )

if __name__ == '__main__':
    if not GOOGLE_API_KEY:
        print("\nWARNING: The Flask server is starting without GOOGLE_API_KEY set.")
    elif not gemini_api_configured:
        print("\nWARNING: Gemini API configuration failed.")
    elif not imagen_client: # This check is after GOOGLE_API_KEY check
        print("\nWARNING: `genai.Client` for Imagen failed to initialize. Image generation may use placeholders.")
    app.run(debug=True, port=5000)
