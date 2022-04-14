"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
from .core import AbstractHandler
import numpy as np
import os
import cv2
import json
import glob
from droidlet.lowlevel.robot_mover_utils import transform_pose
from numba import njit
from math import ceil, floor

# Values for locobot in habitat. 
# TODO: generalize this for all robots
fx, fy = 256, 256
cx, cy = 256, 256
intrinsic_mat = np.array([[  fx, 0., cx],
                            [  0., fy, cy],
                            [  0., 0., 1.]])
# rotation from pyrobot to canonical coordinates (https://github.com/facebookresearch/fairo/blob/main/agents/locobot/coordinates.MD)
rot = np.array([[0.0, 0.0, 1.0], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0]])
CAMERA_HEIGHT = 0.6
trans = np.array([0, 0, CAMERA_HEIGHT])

 # TODO: Consolidate camera intrinsics and their associated utils across locobot and habitat.
def compute_uvone(height, width):
    intrinsic_mat_inv = np.linalg.inv(intrinsic_mat)
    img_resolution = (height, width)
    img_pixs = np.mgrid[0 : img_resolution[0] : 1, 0 : img_resolution[1] : 1]
    img_pixs = img_pixs.reshape(2, -1)
    img_pixs[[0, 1], :] = img_pixs[[1, 0], :]
    uv_one = np.concatenate((img_pixs, np.ones((1, img_pixs.shape[1]))))
    uv_one_in_cam = np.dot(intrinsic_mat_inv, uv_one)
    return uv_one_in_cam, intrinsic_mat, rot, trans

def convert_depth_to_pcd(depth, pose, uv_one_in_cam, rot, trans):
    # point cloud in camera frame
    depth = (depth.astype(np.float32) / 1000.0).reshape(-1)
    pts_in_cam = np.multiply(uv_one_in_cam, depth)
    pts_in_cam = np.concatenate((pts_in_cam, np.ones((1, pts_in_cam.shape[1]))), axis=0)
    # point cloud in robot base frame
    pts_in_base = pts_in_cam[:3, :].T
    pts_in_base = np.dot(pts_in_base, rot.T)
    pts_in_base = pts_in_base + trans.reshape(-1)
    # point cloud in world frame (pyrobot)
    pts_in_world = transform_pose(pts_in_base, pose)
    return pts_in_world

@njit
def get_annot(height, width, pts_in_cur_img, src_pts_in_cur_cam, cur_pts_in_cur_cam, src_label, valid_z):
    """
    This creates the new semantic labels of the projected points in the current image frame. Each new semantic label is the 
    semantic label corresponding to pts_in_cur_img in src_label. 
    """
    annot_img = np.zeros((height, width)).astype(np.float32)
    for indx in range(len(pts_in_cur_img)):
        r = int(indx/width)
        c = int(indx - r*width)
        x, y, _ = pts_in_cur_img[indx]
        
        # We take ceil and floor combinations to fix quantization errors
        if floor(x) >= 0 and ceil(x) < height and floor(y) >=0 and ceil(y) < width and valid_z[indx]:
            cur_indx = ceil(x) + ceil(y) * width
            if src_pts_in_cur_cam[indx][2] - cur_pts_in_cur_cam[cur_indx][2] < 0.01:
                annot_img[ceil(y)][ceil(x)] = src_label[r][c]
                annot_img[floor(y)][floor(x)] = src_label[r][c]
                annot_img[ceil(y)][floor(x)] = src_label[r][c]
                annot_img[floor(y)][ceil(x)] = src_label[r][c]
    
    return annot_img

class LabelPropagate(AbstractHandler):
    def __call__(self,    
        src_img,
        src_depth,
        src_label,
        src_pose,
        cur_pose,
        cur_depth,
    ):
        """
        1. Gets point cloud for the source image 
        2. Transpose the point cloud based on robot location (cur_pose) 
        3. Project the point cloud back into the image frame. The corresponding semantic label for each point from the src_label becomes
        the new semantic label in the current frame.
        Args:
            src_img (np.ndarray): source image to propagte from
            src_depth (np.ndarray): source depth to propagte from
            src_label (np.ndarray): source semantic map to propagte from
            src_pose (np.ndarray): (x,y,theta) of the source image
            cur_pose (np.ndarray): (x,y,theta) of current image
            cur_depth (np.ndarray): current depth
        """

        height, width, _ = src_img.shape
        uv_one_in_cam, intrinsic_mat, rot, trans = compute_uvone(height, width)
        
        src_pts_in_world = convert_depth_to_pcd(src_depth, src_pose, uv_one_in_cam, rot, trans)
        
        # visualize using o3d
        # visualize_pcd(src_pts_in_world)
        
        # convert pts_in_world to current base
        src_pts_in_cur_base = transform_pose(src_pts_in_world, (-cur_pose[0], -cur_pose[1], 0))
        src_pts_in_cur_base = transform_pose(src_pts_in_cur_base, (0.0, 0.0, -cur_pose[2]))
            
        # conver point from current base to current camera frame
        src_pts_in_cur_cam = src_pts_in_cur_base - trans.reshape(-1)
        src_pts_in_cur_cam = np.dot(src_pts_in_cur_cam, rot)
        
        # Get Valid Z
        valid_z = src_pts_in_cur_cam[:,2] > 0
        
        # Filter based on current depth.
        cur_depth = (cur_depth.astype(np.float32) / 1000.0).reshape(-1)
        cur_pts_in_cur_cam = np.multiply(uv_one_in_cam, cur_depth).T 
        
        # conver pts in current camera frame into 2D pix values
        src_pts_in_cur_img = np.matmul(intrinsic_mat, src_pts_in_cur_cam.T).T        
        src_pts_in_cur_img /= src_pts_in_cur_img[:, 2].reshape([-1, 1])
        
        return get_annot(height, width, src_pts_in_cur_img, src_pts_in_cur_cam, cur_pts_in_cur_cam, src_label, valid_z)

