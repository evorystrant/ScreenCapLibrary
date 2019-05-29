#  Copyright 2008-2015 Nokia Networks
#  Copyright 2016-     Robot Framework Foundation
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import os
import time
import threading

try:
    import cv2
    import numpy as np
except ImportError:
    raise ImportError('Importing cv2 failed. Make sure you have opencv-python installed.')

from mss import mss
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures.thread import _threads_queues
from functools import wraps
from robot.api import logger
from robot.utils import get_link_path, abspath, timestr_to_secs, is_truthy
from robot.libraries.BuiltIn import BuiltIn
from .pygtk import _take_gtk_screenshot, _take_partial_gtk_screenshot, _take_gtk_screen_size, _grab_gtk_pb, _record_gtk
from .utils import _norm_path, _compression_value_conversion, _pil_quality_conversion, suppress_stderr

_THREAD_POOL = ThreadPoolExecutor()


def run_in_background(f, executor=None):
    @wraps(f)
    def wrap(*args, **kwargs):
        return (executor or _THREAD_POOL).submit(f, *args, **kwargs)
    return wrap


class Client:

    def __init__(self, screenshot_module=None, screenshot_directory=None, format='png', quality=50, delay=0, fps=8):
        self._screenshot_module = screenshot_module
        self._given_screenshot_dir = _norm_path(screenshot_directory)
        self._format = format
        self._quality = quality
        self._delay = delay
        self.frames = []
        self.name = 'screenshot'
        self.path = None
        self.embed = False
        self.embed_width = None
        self.fps = fps
        self._stop_condition = threading.Event()
        self.futures = None

    @property
    def _screenshot_dir(self):
        return self._given_screenshot_dir or self._log_dir

    @property
    def _log_dir(self):
        variables = BuiltIn().get_variables()
        outdir = variables['${OUTPUTDIR}']
        log = variables['${LOGFILE}']
        log = os.path.dirname(log) if log != 'NONE' else '.'
        return _norm_path(os.path.join(outdir, log))

    def set_screenshot_directory(self, path):
        path = _norm_path(path)
        if not os.path.isdir(path):
            raise RuntimeError("Directory '%s' does not exist." % path)
        old = self._screenshot_dir
        self._given_screenshot_dir = path
        return old

    def _get_screenshot_path(self, basename, format, directory):
        directory = _norm_path(directory) if directory else self._screenshot_dir
        if basename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.webm')):
            return os.path.join(directory, basename)
        index = 0
        while True:
            index += 1
            path = os.path.join(directory, "%s_%d.%s" % (basename, index, format))
            if not os.path.exists(path):
                return path

    @staticmethod
    def _validate_screenshot_path(path):
        path = abspath(_norm_path(path))
        if not os.path.exists(os.path.dirname(path)):
            raise RuntimeError("Directory '%s' where to save the screenshot "
                               "does not exist" % os.path.dirname(path))
        return path

    def _save_screenshot_path(self, basename, format):
        path = self._get_screenshot_path(basename, format, self._screenshot_dir)
        return self._validate_screenshot_path(path)

    def take_screenshot(self, name, format, quality, width='800px', delay=0):
        delay = delay or self._delay
        if delay:
            time.sleep(timestr_to_secs(delay))
        path = self._take_screenshot_client(name, format, quality)
        self._embed_screenshot(path, width)
        return path

    def _take_screenshot_client(self, name, format, quality):
        format = (format or self._format).lower()
        quality = quality or self._quality
        if self._screenshot_module and self._screenshot_module.lower() == 'pygtk':
            return self._take_screenshot_client_gtk(name, format, quality)
        else:
            return self._take_screenshot_client_mss(name, format, quality)

    def _take_screenshot_client_gtk(self, name, format, quality):
        format = 'jpeg' if format == 'jpg' else format
        if format == 'png':
            quality = _compression_value_conversion(quality)
        path = self._save_screenshot_path(name, format)
        if format == 'webp':
            png_img = _take_gtk_screenshot(path, 'png', _compression_value_conversion(100))
            im = Image.open(png_img)
            im.save(path, format, quality=quality)
            return path
        return _take_gtk_screenshot(path, format, quality)

    def _take_screenshot_client_mss(self, name, format, quality):
        if format in ['jpg', 'jpeg', 'webp']:
            with mss() as sct:
                sct_img = sct.grab(sct.monitors[0])
                img = Image.frombytes('RGB', sct_img.size, sct_img.bgra, 'raw', 'BGRX')
                path = self._save_screenshot_path(name, format)
                img.save(path, quality=quality if format == 'webp' else _pil_quality_conversion(quality))
            return path
        elif format == 'png':
            with mss() as sct:
                path_name = self._save_screenshot_path(name, format)
                sct.compression_level = _compression_value_conversion(quality)
                path = sct.shot(mon=-1, output='%s' % path_name)
            return path
        else:
            raise RuntimeError("Invalid screenshot format.")

    def take_multiple_screenshots(self, name, format, quality, screenshot_number, delay_time):
        self.frames = []
        quality = quality or self._quality
        format = (format or self._format).lower()
        format = 'jpeg' if format == 'jpg' else format
        if format == 'png':
            quality = _compression_value_conversion(quality)
        elif format == 'jpeg':
            quality = _pil_quality_conversion(quality)
        delay_time = timestr_to_secs(delay_time)
        self.grab_frames(name, format, quality, delay=delay_time, shot_number=int(screenshot_number))

    def take_partial_screenshot(self, name, format, quality,
                                left, top, width, height, embed, embed_width):
        left = int(left)
        top = int(top)
        width = int(width)
        height = int(height)
        format = (format or self._format).lower()
        quality = quality or self._quality

        if self._screenshot_module and self._screenshot_module.lower() == 'pygtk':
            format = 'jpeg' if format == 'jpg' else format
            if format == 'png':
                quality = _compression_value_conversion(quality)
            path = self._save_screenshot_path(name, format)
            path = _take_partial_gtk_screenshot(path, format, quality, left, top, width, height)
        else:
            try:
                original_image = self.take_screenshot(name, format, quality)
                image = Image.open(original_image)
                box = (left, top, width, height)
                cropped_image = image.crop(box)
                os.remove(original_image)
                path = self._save_screenshot_path(basename=name, format=format)
                cropped_image.save(path, format)
            except IOError:
                raise IOError('File not found.')
            except RuntimeError:
                raise RuntimeError('Taking screenshot failed.')
            except SystemError:
                raise SystemError("Top and left parameters must be lower than screen resolution.")
        if is_truthy(embed):
            self._embed_screenshot(path, embed_width)
        return path

    def take_screenshot_without_embedding(self, name, format, quality, delay):
        delay = delay or self._delay
        if delay:
            time.sleep(timestr_to_secs(delay))
        path = self._take_screenshot_client(name, format, quality)
        self._link_screenshot(path)
        return path

    def start_gif_recording(self, name, size_percentage,
                            embed, embed_width):
        self.name = name
        self.embed = embed
        self.embed_width = embed_width
        self.futures = self.grab_frames(name, size_percentage=size_percentage)

    def _close_threads(self):
        if self.futures._exception:
            raise self.futures._exception
        _THREAD_POOL._threads.clear()
        _threads_queues.clear()

    def stop_gif_recording(self):
        self._close_threads()
        path = self._save_screenshot_path(basename=self.name, format='gif')
        self.frames[0].save(path, save_all=True, append_images=self.frames[1:],
                            duration=125, optimize=True, loop=0)
        if is_truthy(self.embed):
            self._embed_screenshot(path, self.embed_width)
        self.frames = []
        return path

    @run_in_background
    def grab_frames(self, name, format=None, quality=None, size_percentage=0.5, delay=0, shot_number=None):
        if self._screenshot_module and self._screenshot_module.lower() == 'pygtk':
            self._grab_frames_gtk(size_percentage, delay, shot_number)
        else:
            self._grab_frames_mss(size_percentage, delay, shot_number)
        if shot_number:
            for img in self.frames:
                path = self._save_screenshot_path(basename=name, format=format)
                img.save(path, format=format, quality=quality, compress_level=quality)

    def _grab_frames_gtk(self, size_percentage, delay, shot_number):
        width, height = _take_gtk_screen_size()
        w = int(width * size_percentage)
        h = int(height * size_percentage)
        while True:
            pb = _grab_gtk_pb()
            img = Image.frombuffer('RGB', (width, height), pb.get_pixels(), 'raw', 'RGB').resize((w, h))
            self.frames.append(img)
            if delay:
                time.sleep(timestr_to_secs(delay))
            if shot_number and len(self.frames) == int(shot_number):
                break
            time.sleep(0.125)

    def _grab_frames_mss(self, size_percentage, delay, shot_number):
        with mss() as sct:
            width = int(sct.grab(sct.monitors[0]).size.width * size_percentage)
            height = int(sct.grab(sct.monitors[0]).size.height * size_percentage)
            while True:
                sct_img = sct.grab(sct.monitors[0])
                img = Image.frombytes('RGB', sct_img.size, sct_img.bgra, 'raw', 'BGRX').resize((width, height))
                self.frames.append(img)
                if delay:
                    time.sleep(timestr_to_secs(delay))
                if shot_number and len(self.frames) == int(shot_number):
                    break

    def _embed_screenshot(self, path, width):
        link = get_link_path(path, self._log_dir)
        logger.info('<a href="%s"><img src="%s" width="%s"></a>' % (link, link, width), html=True)

    def _embed_video(self, path, width):
        link = get_link_path(path, self._log_dir)
        logger.info('<a href="%s"><video width="%s" autoplay><source src="%s" type="video/webm"></video></a>' %
                    (link, width, link), html=True)

    def _link_screenshot(self, path):
        link = get_link_path(path, self._log_dir)
        logger.info("Screenshot saved to '<a href=\"%s\">%s</a>'." % (link, path), html=True)

    def start_video_recording(self, name, fps, embed, embed_width):
        self.name = name
        try:
            self.fps = int(fps)
        except ValueError:
            raise ValueError('The fps argument must be of type integer.')
        self.embed = embed
        self.embed_width = embed_width
        self.path = self._save_screenshot_path(basename=self.name, format='webm')
        self.futures = self.capture_screen(self.path, self.fps)

    def stop_video_recording(self):
        self._stop_condition.set()
        self._close_threads()
        if is_truthy(self.embed):
            self._embed_video(self.path, self.embed_width)
        return self.path

    @run_in_background
    def capture_screen(self, path, fps):
        if self._screenshot_module and self._screenshot_module.lower() == 'pygtk':
            _record_gtk(path, fps, stop=self._stop_condition)
        else:
            self._record_mss(path, fps)

    def _record_mss(self, path, fps):
        fourcc = cv2.VideoWriter_fourcc(*'VP08')
        with mss() as sct:
            sct_img = sct.grab(sct.monitors[1])
        width = int(sct_img.width)
        height = int(sct_img.height)
        with suppress_stderr():
            vid = cv2.VideoWriter('%s' % path, fourcc, fps, (width, height))
        while not self._stop_condition.isSet():
            with mss() as sct:
                sct_img = sct.grab(sct.monitors[1])
            numpy_array = np.array(sct_img)
            frame = cv2.cvtColor(numpy_array, cv2.COLOR_RGBA2RGB)
            vid.write(frame)
        vid.release()
        cv2.destroyAllWindows()