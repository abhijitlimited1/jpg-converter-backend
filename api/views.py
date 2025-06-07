import os
import sys
import img2pdf
from pdf2image import convert_from_bytes
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from io import BytesIO
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Set up Poppler path if not already set
if not os.environ.get('POPPLER_PATH'):
    # Try to find Poppler in the project directory
    base_dir = Path(__file__).parent.parent.parent  # Go up to backend directory
    
    # Check different possible Poppler paths
    possible_paths = [
        base_dir / "poppler" / "poppler-23.11.0" / "Library" / "bin",  # This is the path we found
        base_dir / "poppler" / "Library" / "bin",
        base_dir / "poppler" / "bin",
        base_dir / "poppler-23.11.0" / "Library" / "bin",
    ]
    
    poppler_path = None
    for path in possible_paths:
        if path.exists():
            poppler_path = str(path)
            logger.info(f"Found Poppler at: {poppler_path}")
            break
    
    if poppler_path:
        os.environ['POPPLER_PATH'] = poppler_path
        logger.info(f"POPPLER_PATH automatically set to: {poppler_path}")
    else:
        # Try to install Poppler
        try:
            logger.info("Attempting to install Poppler...")
            install_script = base_dir / "install_poppler.py"
            
            if install_script.exists():
                # Execute the install script
                import subprocess
                result = subprocess.run([sys.executable, str(install_script)], 
                                       capture_output=True, text=True)
                
                # Check if installation was successful
                if result.returncode == 0 and "Poppler installed at:" in result.stdout:
                    # Extract the path from the output
                    import re
                    match = re.search(r"Poppler installed at: (.*)", result.stdout)
                    if match:
                        poppler_path = match.group(1)
                        os.environ['POPPLER_PATH'] = poppler_path
                        logger.info(f"POPPLER_PATH set to: {poppler_path}")
                    else:
                        logger.warning("Could not extract Poppler path from installation output")
                else:
                    logger.warning(f"Poppler installation failed: {result.stderr}")
            else:
                logger.warning(f"Install script not found at {install_script}")
        except Exception as e:
            logger.error(f"Error installing Poppler: {e}")
            logger.warning("Poppler not found. PDF to image conversion may not work correctly.")

class JpgToPdfView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        try:
            images = request.FILES.getlist('images')
            if not images:
                return HttpResponse("No images provided", status=400)
            
            image_data = [img.read() for img in images]
            pdf_bytes = img2pdf.convert(image_data)
            
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="converted.pdf"'
            return response
        except Exception as e:
            logger.error(f"JPG to PDF conversion error: {str(e)}")
            return HttpResponse(f"Conversion failed: {str(e)}", status=500)

class PdfToJpgView(APIView):
    parser_classes = [MultiPartParser]
    
    def head(self, request):
        # Handle HEAD requests for server availability check
        return HttpResponse(status=200)
        
    def post(self, request):
        try:
            pdf_file = request.FILES['pdf']  # Will raise KeyError if missing
            format = request.POST.get('format', 'jpg').lower()
            
            logger.info(f"Processing PDF to {format} conversion for file: {pdf_file.name}")
            
            # Get PDF content
            pdf_content = pdf_file.read()
            
            # Log file size for debugging
            file_size_mb = len(pdf_content) / (1024 * 1024)
            logger.info(f"PDF file size: {file_size_mb:.2f} MB")
            
            # Check if Poppler path is set
            poppler_path = os.environ.get('POPPLER_PATH')
            logger.info(f"Current POPPLER_PATH: {poppler_path}")
            
            # Try to find Poppler if not set
            if not poppler_path:
                base_dir = Path(__file__).parent.parent.parent
                for path in [
                    base_dir / "poppler" / "poppler-23.11.0" / "Library" / "bin",
                    base_dir / "poppler" / "Library" / "bin",
                ]:
                    if path.exists():
                        poppler_path = str(path)
                        os.environ['POPPLER_PATH'] = poppler_path
                        logger.info(f"Found and set POPPLER_PATH to: {poppler_path}")
                        break
            
            # Verify Poppler path exists
            if poppler_path and not Path(poppler_path).exists():
                logger.warning(f"Specified POPPLER_PATH does not exist: {poppler_path}")
                poppler_path = None
            
            # Try conversion with explicit options
            try:
                logger.info("Attempting PDF conversion with explicit options")
                conversion_options = {
                    'fmt': format,
                    'use_pdftocairo': True,  # Try using pdftocairo for better quality
                    'timeout': 60,  # Increase timeout for large files
                }
                
                if poppler_path:
                    conversion_options['poppler_path'] = poppler_path
                    logger.info(f"Using poppler_path: {poppler_path}")
                
                images = convert_from_bytes(pdf_content, **conversion_options)
                logger.info(f"Successfully converted PDF to {len(images)} images")
                
            except Exception as first_error:
                logger.warning(f"First conversion attempt failed: {str(first_error)}")
                
                # Try alternative conversion method
                try:
                    logger.info("Attempting alternative conversion method")
                    conversion_options = {
                        'fmt': format,
                        'use_pdftocairo': False,  # Try without pdftocairo
                    }
                    
                    if poppler_path:
                        conversion_options['poppler_path'] = poppler_path
                    
                    images = convert_from_bytes(pdf_content, **conversion_options)
                    logger.info(f"Alternative conversion succeeded with {len(images)} images")
                    
                except Exception as second_error:
                    logger.error(f"All conversion attempts failed: {str(second_error)}")
                    return HttpResponse(
                        "PDF conversion failed. The PDF might be corrupted, password-protected, or Poppler is not properly installed.",
                        status=500
                    )
            
            if not images:
                return HttpResponse("Failed to extract images from PDF (no images extracted)", status=500)
                
            output = BytesIO()
            
            if len(images) == 1:
                # Single page PDF
                logger.info("Processing single page PDF")
                # Ensure proper format for PNG/JPG
                if format.lower() == 'png':
                    images[0].save(output, format='PNG', compress_level=1)  # Lower compression for better quality
                    logger.info("Saved as PNG with high quality")
                else:
                    images[0].save(output, format='JPEG', quality=95)  # High quality JPEG
                    logger.info("Saved as JPEG with high quality")
                content_type = f'image/{format}'
                filename = f'converted.{format}'
            else:
                # Multi-page PDF - create ZIP
                logger.info(f"Processing multi-page PDF with {len(images)} pages")
                from zipfile import ZipFile
                with BytesIO() as zip_buffer:
                    with ZipFile(zip_buffer, 'w') as zip_file:
                        for i, image in enumerate(images):
                            img_buffer = BytesIO()
                            # Ensure proper format for PNG/JPG
                            if format.lower() == 'png':
                                image.save(img_buffer, format='PNG', compress_level=1)  # Lower compression for better quality
                            else:
                                image.save(img_buffer, format='JPEG', quality=95)  # High quality JPEG
                            img_buffer.seek(0)
                            zip_file.writestr(f'page_{i+1}.{format}', img_buffer.getvalue())
                    output.write(zip_buffer.getvalue())
                content_type = 'application/zip'
                filename = 'converted.zip'
            
            # Reset buffer position
            output.seek(0)
            
            # Log success
            output_size_mb = len(output.getvalue()) / (1024 * 1024)
            logger.info(f"Conversion successful. Output size: {output_size_mb:.2f} MB, Content-Type: {content_type}")
            
            response = HttpResponse(output.getvalue(), content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
        except KeyError:
            logger.warning("No PDF file uploaded")
            return HttpResponse("No PDF file uploaded", status=400)
        except Exception as e:
            logger.error(f"PDF to JPG conversion error: {str(e)}", exc_info=True)
            return HttpResponse(f"Conversion failed: {str(e)}", status=500)