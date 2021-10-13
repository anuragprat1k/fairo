"""
Copyright (c) Facebook, Inc. and its affiliates.
"""

import logging
import threading
import time

from typing import List

from .data_generator import DataGenerator


class JobListener:
    def __init__(self, timeout=-1):
        self._finished = False
        self._started = False
        self.start_time = time.time()
        self.timeout = timeout  # in minutes, -1 if no timeout is set
        self._parent_jobs = []

    def run(self):
        pass

    def start(self, *args):
        if not self._started:
            thread = threading.Thread(target=self.run, args=(args))
            thread.daemon = True
            thread.start()
            self._started = True

    def set_finished(self, finished=True):
        self._finished = finished

    def check_is_finished(self) -> bool:
        return self._finished

    def check_parent_finished(self) -> bool:
        finished = True
        for job in self._parent_jobs:
            if not job.check_is_finished():
                finished = False
        return finished

    def add_parent_jobs(self, jobs: List[DataGenerator]):
        self._parent_jobs.extend(jobs)

    def check_is_timeout(self) -> bool:
        if self.timeout == -1:
            return False

        if time.time() - self.start_time < self.timeout * 60:
            return False
        return True

    def get_remaining_time(self) -> int:
        return self.timeout - ((time.time() - self.start_time) // 60)