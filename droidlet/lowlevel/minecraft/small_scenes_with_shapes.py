"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import numpy as np
import random
from droidlet.lowlevel.minecraft.iglu_util import IGLU_BLOCK_MAP
from droidlet.lowlevel.minecraft.shape_util import (
    SHAPE_NAMES,
    SHAPE_FNS,
    SHAPE_OPTION_FUNCTION_MAP,
)

SL = 17
GROUND_DEPTH = 5
H = 13


def bid():
    return (35, np.random.randint(16))


def red():
    return (35, 14)


def white():
    return (35, 0)


# ignoring blocks for now
def avatar_pos(args, blocks):
    return (1, args.GROUND_DEPTH, 1)


def avatar_look(args, blocks):
    return (0.0, 0.0)


def agent_pos(args, blocks):
    return (3, args.GROUND_DEPTH, 0)


def agent_look(args, blocks):
    return (0.0, 0.0)


def build_base_world(sl, h, g, fence=False):
    W = []
    for i in range(sl):
        for j in range(g):
            for k in range(sl):
                if (i == 0 or i == sl - 1 or k == 0 or k == sl - 1) and j == g - 1 and fence:
                    idm = red()
                else:
                    idm = white()
                W.append(((i, j, k), idm))
    return W


def build_shape_scene(args):
    """
    Build a scene using basic shapes,
    outputs a json dict with fields
    "avatarInfo" = {"pos": (x,y,z), "look": (yaw, pitch)}
    "agentInfo" = {"pos": (x,y,z), "look": (yaw, pitch)}
    "blocks" = [(x,y,z,bid) ... (x,y,z,bid)]
    "schematic_for_cuberite" = [{"x": x, "y":y, "z":z, "id":blockid, "meta": meta} ...]
    where bid is the output of the BLOCK_MAP applied to a minecraft blockid, meta pair.
    """
    fence = getattr(args, "fence", False)
    blocks = build_base_world(args.SL, args.H, args.GROUND_DEPTH, fence=fence)
    print(len(blocks))
    num_shapes = np.random.randint(1, args.MAX_NUM_SHAPES + 1)
    print(num_shapes)
    for t in range(num_shapes):
        shape = random.choice(SHAPE_NAMES)
        opts = SHAPE_OPTION_FUNCTION_MAP[shape]()
        opts["bid"] = bid()
        S = SHAPE_FNS[shape](**opts)
        m = np.mean([l for l, idm in S], axis=0)
        offsets = np.random.randint((args.SL, args.H, args.SL)) - m
        for l, idm in S:
            ln = np.add(l, offsets)
            if ln[0] >= 0 and ln[1] >= 0 and ln[2] >= 0:
                if ln[0] < args.SL and ln[1] < args.H and ln[2] < args.SL:
                    blocks.append((ln, idm))
        print(len(blocks))
    J = {}
    J["avatarInfo"] = {"pos": avatar_pos(args, blocks), "look": avatar_look(args, blocks)}
    J["agentInfo"] = {"pos": agent_pos(args, blocks), "look": agent_look(args, blocks)}
    J["schematic_for_cuberite"] = [
        {
            "x": l[0] + args.cuberite_x_offset,
            "y": l[1] + args.cuberite_y_offset,
            "z": l[2] + args.cuberite_z_offset,
            "id": idm[0],
            "meta": idm[1],
        }
        for l, idm in blocks
    ]
    transformed_blocks = [(l[0], l[1], l[2], IGLU_BLOCK_MAP[idm]) for l, idm in blocks]
    J["blocks"] = transformed_blocks
    return J


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--SL", type=int, default=SL)
    parser.add_argument("--H", type=int, default=H)
    parser.add_argument("--GROUND_DEPTH", type=int, default=GROUND_DEPTH)
    parser.add_argument("--MAX_NUM_SHAPES", type=int, default=3)
    parser.add_argument("--NUM_SCENES", type=int, default=3)
    parser.add_argument("--fence", action="store_true", default=False)
    parser.add_argument("--cuberite_x_offset", type=int, default=-SL // 2)
    parser.add_argument("--cuberite_y_offset", type=int, default=63 - GROUND_DEPTH)
    parser.add_argument("--cuberite_z_offset", type=int, default=-SL // 2)
    parser.add_argument("--save_data_path", default="")
    args = parser.parse_args()

    scenes = []
    for i in range(args.NUM_SCENES):
        scenes.append(build_shape_scene(args))
    if args.NUM_SCENES == 1:
        scenes = scenes[0]
    if args.save_data_path:
        with open(args.save_data_path, "w") as f:
            json.dump(scenes, f)