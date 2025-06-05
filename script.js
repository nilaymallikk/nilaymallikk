document.addEventListener('DOMContentLoaded', () => {
    const topicInput = document.getElementById('topicInput');
    const generateButton = document.getElementById('generateButton');
    const slideshowArea = document.getElementById('slideshowArea');
    const downloadButton = document.getElementById('downloadButton');

    let slidesDataGlobal = []; // Stores the full slide data for download

    if (downloadButton) {
        downloadButton.classList.add('hidden');
    }

    if (generateButton) {
        generateButton.addEventListener('click', async () => {
            const topic = topicInput.value.trim();

            if (!topic) {
                slideshowArea.innerHTML = '<p style="color: red;">Please enter a topic.</p>';
                return;
            }

            slideshowArea.innerHTML = '<p>Loading presentation...</p>';
            generateButton.disabled = true;
            if (downloadButton) downloadButton.classList.add('hidden');
            slidesDataGlobal = []; // Clear previous data

            try {
                const response = await fetch('/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ topic: topic }),
                });

                if (!response.ok) {
                    let errorMsg = `Server error: ${response.status}`;
                    try {
                        const errorData = await response.json();
                        errorMsg = errorData.error || errorMsg;
                    } catch (e) {
                        // If parsing error data fails, use the status text
                        errorMsg = response.statusText || errorMsg;
                    }
                    throw new Error(errorMsg);
                }

                const slides = await response.json();

                if (slides && slides.length > 0) {
                    slidesDataGlobal = slides; // Store for download
                    showSlide(0, slidesDataGlobal);
                } else {
                    slideshowArea.innerHTML = '<p>No content received, or content is empty.</p>';
                    generateButton.disabled = false;
                }

            } catch (error) {
                slideshowArea.innerHTML = `<p style="color: red;">Error: ${error.message}</p>`;
                generateButton.disabled = false;
            }
        });
    }

    function showSlide(index, slidesArray) {
        if (index >= slidesArray.length) {
            slideshowArea.innerHTML = '<h2>Presentation Preview Complete!</h2><p>You can now download the presentation content.</p>';
            if (downloadButton) downloadButton.classList.remove('hidden');
            if (generateButton) generateButton.disabled = false;
            return;
        }

        const slide = slidesArray[index];
        slideshowArea.innerHTML = '';

        const img = document.createElement('img');
        img.src = slide.imageUrl; // This could be a placeholder or a data URI
        img.alt = slide.imagePrompt || "Slide image";
        img.style.maxWidth = '100%';
        img.style.maxHeight = '400px';
        img.style.marginBottom = '10px';
        img.onerror = () => { // Handle broken image links/placeholders gracefully
            img.alt = "Image failed to load or is a placeholder.";
            img.src = 'https://via.placeholder.com/600x400.png?text=Image+Load+Error'; // Fallback visual
        };


        const p = document.createElement('p');
        p.textContent = slide.sentence;
        p.style.fontSize = '1.2em';

        slideshowArea.appendChild(img);
        slideshowArea.appendChild(p);

        setTimeout(() => {
            showSlide(index + 1, slidesArray);
        }, 3000);
    }

    if (downloadButton) {
        downloadButton.addEventListener('click', async () => {
            if (!slidesDataGlobal || slidesDataGlobal.length === 0) {
                alert("No slide data available to download.");
                return;
            }

            const originalButtonText = downloadButton.textContent;
            downloadButton.disabled = true;
            downloadButton.textContent = 'Preparing download...';

            try {
                const response = await fetch('/download', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ slides: slidesDataGlobal }),
                });

                if (!response.ok) {
                    let errorMsg = `Download failed: ${response.status}`;
                    try {
                        const errorData = await response.json(); // Server might send JSON error
                        errorMsg = errorData.error || errorMsg;
                    } catch (e) {
                        // If error response isn't JSON
                        errorMsg = (await response.text()) || errorMsg;
                    }
                    throw new Error(errorMsg);
                }

                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = 'monkey_banana_slideshow.zip';
                document.body.appendChild(a);
                a.click();
                URL.revokeObjectURL(url);
                document.body.removeChild(a);

                downloadButton.textContent = 'Download Complete!';
                setTimeout(() => { downloadButton.textContent = originalButtonText; }, 3000);


            } catch (error) {
                alert(`Error during download: ${error.message}`);
                downloadButton.textContent = 'Download Failed!';
                setTimeout(() => { downloadButton.textContent = originalButtonText; }, 3000);
            } finally {
                downloadButton.disabled = false;
            }
        });
    }
});
