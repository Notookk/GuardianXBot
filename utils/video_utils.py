import os
import cv2
import logging
import subprocess
import tempfile
from typing import List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def capture_screenshots(
    video_path: str,
    output_dir: str = "screenshots",
    interval_seconds: int = 10,
    max_frames: Optional[int] = None
) -> List[str]:
    """
    Capture screenshots from video at regular intervals.
    
    Args:
        video_path: Path to input video file
        output_dir: Directory to save screenshots
        interval_seconds: Seconds between captures
        max_frames: Maximum number of frames to capture (None for no limit)
        
    Returns:
        List of paths to saved screenshot images
    """
    os.makedirs(output_dir, exist_ok=True)
    frames = []
    vid_obj = None
    
    try:
        vid_obj = cv2.VideoCapture(video_path)
        if not vid_obj.isOpened():
            raise IOError(f"Could not open video file: {video_path}")

        fps = vid_obj.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30  # Default fallback
            logger.warning(f"Couldn't read FPS, using default {fps}")

        total_frames = int(vid_obj.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_interval = int(fps * interval_seconds)
        
        logger.info(f"Processing video: {video_path}")
        logger.info(f"Total frames: {total_frames}, Capture interval: {frame_interval} frames")

        count = 0
        while True:
            if max_frames and len(frames) >= max_frames:
                break
                
            ret, frame = vid_obj.read()
            if not ret:
                break

            if count % frame_interval == 0:
                frame_path = os.path.join(output_dir, f"screenshot_{count:06d}.png")
                if not cv2.imwrite(frame_path, frame):
                    raise IOError(f"Failed to write frame {count} to {frame_path}")
                frames.append(frame_path)
                logger.debug(f"Captured frame {count}")

            count += 1

    except Exception as e:
        logger.error(f"Error capturing screenshots: {e}", exc_info=True)
        # Clean up partially captured frames if error occurs
        for frame in frames:
            try:
                os.remove(frame)
            except:
                pass
        frames = []
    finally:
        if vid_obj and vid_obj.isOpened():
            vid_obj.release()

    logger.info(f"Captured {len(frames)} frames from {video_path}")
    return frames

def convert_webm_to_png(
    webm_path: str,
    output_path: Optional[str] = None,
    frame_time: str = "00:00:00"
) -> Optional[str]:
    """
    Convert WEBM video to PNG image using FFmpeg.
    
    Args:
        webm_path: Path to input WEBM file
        output_path: Optional custom output path
        frame_time: Timecode to extract frame (HH:MM:SS)
        
    Returns:
        Path to generated PNG file or None if failed
    """
    if not os.path.exists(webm_path):
        logger.error(f"Input file not found: {webm_path}")
        return None

    try:
        if not output_path:
            output_path = f"{tempfile.mktemp()}.png"

        command = [
            "ffmpeg",
            "-y",  # Overwrite without asking
            "-ss", frame_time,  # Seek to specified time
            "-i", webm_path,
            "-vframes", "1",  # Capture single frame
            "-q:v", "2",  # Quality level (2-31, lower is better)
            "-f", "image2",
            output_path
        ]

        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if not os.path.exists(output_path):
            raise IOError(f"FFmpeg failed to create output file: {output_path}")

        logger.info(f"Converted WEBM to PNG: {webm_path} -> {output_path}")
        return output_path

    except subprocess.CalledProcessError as e:
        logger.error(
            f"FFmpeg conversion failed (code {e.returncode}):\n"
            f"Command: {' '.join(e.cmd)}\n"
            f"Error: {e.stderr}"
        )
    except Exception as e:
        logger.error(f"WEBM conversion error: {e}", exc_info=True)
    
    # Cleanup if failed
    if output_path and os.path.exists(output_path):
        try:
            os.remove(output_path)
        except:
            pass
    
    return None

def extract_video_frames(
    video_path: str,
    frames: int = 3,
    output_dir: str = "frames"
) -> List[str]:
    """
    Extract evenly spaced frames from video.
    
    Args:
        video_path: Path to input video
        frames: Number of frames to extract
        output_dir: Output directory
        
    Returns:
        List of frame file paths
    """
    os.makedirs(output_dir, exist_ok=True)
    result = []
    cap = None
    
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise IOError(f"Could not open video: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_indices = np.linspace(0, total_frames-1, frames, dtype=int)
        
        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                frame_path = os.path.join(output_dir, f"frame_{idx:06d}.jpg")
                if cv2.imwrite(frame_path, frame):
                    result.append(frame_path)
                else:
                    logger.warning(f"Failed to write frame {idx}")
    except Exception as e:
        logger.error(f"Frame extraction failed: {e}", exc_info=True)
    finally:
        if cap and cap.isOpened():
            cap.release()
    
    return result