import os
import random
import numpy as np
import matplotlib.pyplot as plt
import cv2
import json

def get_cache_key(data_dir, img_id, good, evenly_spaced):
    return data_dir + '_' + str(img_id) + '_' + str(good) + '_' + str(evenly_spaced)

def cached(file_name):
    def decorator(original_func):
        try:
            cache = json.load(open(file_name, 'r'))
        except (IOError, ValueError):
            cache = {}
        
        def new_func(sample_class, img_id, good, evenly_spaced):
            k = get_cache_key(sample_class.data_dir, img_id, good, evenly_spaced)
            if k in cache:
                return cache[k]
            val = original_func(sample_class, img_id, good, evenly_spaced)
            cache[k] = val
            json.dump(cache, open(file_name, 'w'))
            return val
        return new_func
    
    return decorator

class SampleGoodCandidates:
    def __init__(self, data_dir, is_annot_validfn):
        self.data_dir = data_dir
        self.img_dir = os.path.join(data_dir, 'rgb')
        self.seg_dir = os.path.join(data_dir, 'seg')
        self.good_candidates = []
        self.bad_candidates = []
        self.is_annot_validfn = is_annot_validfn
        self.filter_candidates()
    
    def filter_candidates(self):
        for x in os.listdir(self.img_dir):
            def get_id_from_filename(x):
                return int(x.split('.')[0])
            img_id = get_id_from_filename(x)
            if self.is_good_candidate(img_id):
                self.good_candidates.append(img_id)
            else:
                self.bad_candidates.append(img_id)
                
        print(f'{len(self.good_candidates)} good candidates found!')
    
    def is_good_candidate(self, x):
        """
        checks if an image is a good candidate by checking that the mask is within a certain distance from the 
        boundary (to approximate the object being in view) and that the area of the mask is greater than a certain 
        threshold
        """
        seg_path = os.path.join(self.seg_dir, "{:05d}.npy".format(x))
        if not os.path.isfile(seg_path):
            return False
        
        # Load Annotations 
        annot = np.load(seg_path).astype(np.uint32)
        all_binary_mask = np.zeros_like(annot)
        
        for i in np.sort(np.unique(annot.reshape(-1), axis=0)):
            if self.is_annot_validfn(i):
                binary_mask = (annot == i).astype(np.uint8)
                # if binary_mask.sum() < 5000:
                #     return False
                all_binary_mask = np.bitwise_or(binary_mask, all_binary_mask)
                
        if not all_binary_mask.any():
            return False
        
        # Check that all masks are within a certain distance from the boundary
        # all pixels [:10,:], [:,:10], [-10:], [:-10] must be 0:
        if all_binary_mask[:10,:].any() or all_binary_mask[:,:10].any() or all_binary_mask[:,-10:].any() or all_binary_mask[-10:,:].any():
            return False
        
        if all_binary_mask.sum() < 5000:
            return False
        
        return True
    
    # @cached('/checkpoint/apratik/candidates_cached_instance_sanity.json')
    def get_n_candidates(self, n, good, evenly_spaced=False):
        # go through the images and filter candidates
        # mark all the good candidates and then uniformly sample from them 
        # Pick n things uniformly from all the good candidates
        def sample_even_or_random(arr, n, evenly_spaced=False):
            if len(arr) == 0:
                return []

            if evenly_spaced:
                return [arr[int(x)] for x in np.linspace(0, len(arr), n, endpoint=False)]
            else:
                return random.sample(arr, min(len(arr), n))

        if good:
            return sample_even_or_random(self.good_candidates, n, evenly_spaced)
        else:
            return sample_even_or_random(self.bad_candidates, n, evenly_spaced)
    
    def visualize(self, candidates):
        fig, axs = plt.subplots(1, len(candidates), figsize=(2*len(candidates),4))
        for x in range(len(candidates)):
            img_path = os.path.join(self.img_dir, "{:05d}.jpg".format(candidates[x]))
            seg_path = os.path.join(self.seg_dir, "{:05d}.npy".format(candidates[x]))
            annot = np.load(seg_path).astype(np.uint32)
            all_binary_mask = np.zeros_like(annot)
            for i in np.sort(np.unique(annot.reshape(-1), axis=0)):
                if self.is_annot_validfn(i):
                    binary_mask = (annot == i).astype(np.uint8)
                    all_binary_mask = np.bitwise_or(binary_mask, all_binary_mask)
            
            image = cv2.cvtColor(cv2.imread(img_path), cv2.COLOR_BGR2RGB)
            color = np.asarray(np.random.choice(range(256), size=3))
            image[all_binary_mask == 1] = image[all_binary_mask == 1] * 0.4 + color * 0.6
            axs[x].imshow(image)
            axs[x].set_title("{:05d}.jpg".format(x))
        plt.show()