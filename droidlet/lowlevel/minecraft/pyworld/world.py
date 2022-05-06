"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import numpy as np
from typing import Sequence, Dict
from droidlet.base_util import Pos, Look
from droidlet.lowlevel.minecraft.mc_util import Block, XYZ, IDM
from droidlet.shared_data_struct.craftassist_shared_utils import Player
from droidlet.shared_data_struct.rotation import look_vec
from droidlet.lowlevel.minecraft.pyworld.fake_mobs import make_mob_opts, MOB_META, SimpleMob
from droidlet.lowlevel.minecraft.pyworld.utils import build_ground, make_pose


def shift_coords(p, shift):
    if hasattr(p, "x"):
        return Pos(p.x + shift[0], p.y + shift[1], p.z + shift[2])
    q = np.add(p, shift)
    if type(p) is tuple:
        q = tuple(q)
    if type(p) is list:
        q = list(q)
    return q


def build_coord_shifts(coord_shift):
    def to_world_coords(p):
        dx = -coord_shift[0]
        dy = -coord_shift[1]
        dz = -coord_shift[2]
        return shift_coords(p, (dx, dy, dz))

    def from_world_coords(p):
        return shift_coords(p, coord_shift)

    return to_world_coords, from_world_coords


class World:
    def __init__(self, opts, spec):
        self.opts = opts
        self.count = 0
        self.sl = opts.sl

        # to be subtracted from incoming coordinates and added to outgoing
        self.coord_shift = spec.get("coord_shift", (0, 0, 0))
        to_world_coords, from_world_coords = build_coord_shifts(self.coord_shift)
        self.to_world_coords = to_world_coords
        self.from_world_coords = from_world_coords

        self.blocks = np.zeros((opts.sl, opts.sl, opts.sl, 2), dtype="int32")
        if spec.get("ground_generator"):
            ground_args = spec.get("ground_args", None)
            if ground_args is None:
                spec["ground_generator"](self)
            else:
                spec["ground_generator"](self, **ground_args)
        else:
            build_ground(self)
        self.mobs = []
        for m in spec["mobs"]:
            m.add_to_world(self)
        self.item_stacks = []
        for i in spec["item_stacks"]:
            i.add_to_world(self)
        self.players = {}
        for p in spec["players"]:
            if hasattr(p, "add_to_world"):
                p.add_to_world(self)
            else:
                self.players[p.entityId] = p
        self.agent_data = spec["agent"]
        self.chat_log = []

        # FIXME
        self.mob_opt_maker = make_mob_opts
        self.mob_maker = SimpleMob

        # TODO: Add item stack maker?

        if hasattr(opts, "world_server") and opts.world_server:
            port = getattr(opts, "port", 25565)
            self.setup_server(port=port)

    def set_count(self, count):
        self.count = count

    def step(self):
        for m in self.mobs:
            m.step()
        for eid, p in self.players.items():
            if hasattr(p, "step"):
                p.step()
        self.count += 1

    def place_block(self, block: Block, force=False):
        loc, idm = block
        if idm[0] == 383:
            # its a mob...
            try:
                # FIXME handle unknown mobs/mobs not in list
                m = SimpleMob(make_mob_opts(MOB_META[idm[1]]), start_pos=loc)
                m.agent_built = True
                m.add_to_world(self)
                return True
            except:
                return False
        # mobs keep loc in real coords, block objects we convert to the numpy index
        loc = tuple(self.to_world_coords(loc))
        if idm[0] == 0:
            try:
                if tuple(self.blocks[loc]) != (7, 0) or force:
                    self.blocks[loc] = (0, 0)
                    return True
                else:
                    return False
            except:
                return False
        else:
            try:
                if tuple(self.blocks[loc]) != (7, 0) or force:
                    self.blocks[loc] = idm
                    return True
                else:
                    return False
            except:
                return False

    def dig(self, loc: XYZ):
        return self.place_block((loc, (0, 0)))

    def blocks_to_dict(self):
        d = {}
        nz = np.transpose(self.blocks[:, :, :, 0].nonzero())
        for loc in nz:
            l = tuple(loc.tolist())
            d[self.from_world_coords(l)] = tuple(self.blocks[l[0], l[1], l[2], :])
        return d

    def get_idm_at_locs(self, xyzs: Sequence[XYZ]) -> Dict[XYZ, IDM]:
        """Return the ground truth block state"""
        d = {}
        for (x, y, z) in xyzs:
            B = self.get_blocks(x, x, y, y, z, z)
            d[(x, y, z)] = tuple(B[0, 0, 0, :])
        return d

    def get_mobs(self):
        return [m.get_info() for m in self.mobs]

    def get_player_info(self, eid):
        """
        returns a Player struct
        or None if eid is not a player
        it is assumed that if p implements its own get_info() method, that
        returns a Player struct
        """
        p = self.players.get(eid)
        if not p:
            return
        if hasattr(p, "get_info"):
            return p.get_info()
        else:
            return p

    def get_players(self):
        return [self.get_player_info(eid) for eid in self.players]

    def get_item_stacks(self):
        return [i.get_info() for i in self.item_stacks]

    def get_blocks(self, xa, xb, ya, yb, za, zb, transpose=True):
        xa, ya, za = self.to_world_coords((xa, ya, za))
        xb, yb, zb = self.to_world_coords((xb, yb, zb))
        M = np.array((xb, yb, zb))
        m = np.array((xa, ya, za))
        szs = M - m + 1
        B = np.zeros((szs[1], szs[2], szs[0], 2), dtype="uint8")
        B[:, :, :, 0] = 7
        xs, ys, zs = [0, 0, 0]
        xS, yS, zS = szs
        if xb < 0 or yb < 0 or zb < 0:
            return B
        if xa > self.sl - 1 or ya > self.sl - 1 or za > self.sl - 1:
            return B
        if xb > self.sl - 1:
            xS = self.sl - xa
            xb = self.sl - 1
        if yb > self.sl - 1:
            yS = self.sl - ya
            yb = self.sl - 1
        if zb > self.sl - 1:
            zS = self.sl - za
            zb = self.sl - 1
        if xa < 0:
            xs = -xa
            xa = 0
        if ya < 0:
            ys = -ya
            ya = 0
        if za < 0:
            zs = -za
            za = 0
        pre_B = self.blocks[xa : xb + 1, ya : yb + 1, za : zb + 1, :]
        # pre_B = self.blocks[ya : yb + 1, za : zb + 1, xa : xb + 1, :]
        B[ys:yS, zs:zS, xs:xS, :] = pre_B.transpose(1, 2, 0, 3)
        if transpose:
            return B
        else:
            return pre_B

    def get_line_of_sight(self, pos, yaw, pitch):
        # it is assumed lv is unit normalized
        pos = tuple(self.to_world_coords(pos))
        lv = look_vec(yaw, pitch)
        dt = 1.0
        for n in range(2 * self.sl):
            p = tuple(np.round(np.add(pos, n * dt * lv)).astype("int32"))
            for i in range(-1, 2):
                for j in range(-1, 2):
                    for k in range(-1, 2):
                        sp = tuple(np.add(p, (i, j, k)))
                        if all([x >= 0 for x in sp]) and all([x < self.sl for x in sp]):
                            if tuple(self.blocks[sp]) != (0, 0):
                                # TODO: deal with close blocks artifacts,
                                # etc
                                pos = self.from_world_coords(sp)
                                return tuple(int(l) for l in pos)
        return

    def add_incoming_chat(self, chat: str, speaker_name: str):
        """Add a chat to memory as if it was just spoken by SPEAKER"""
        self.chat_log.append("<" + speaker_name + ">" + " " + chat)

    def connect_player(self, sid, data):
        # FIXME, this probably won't actually work
        if self.connected_sids.get(sid) is not None:
            print("reconnecting eid {} (sid {})".format(self.connected_sids["sid"], sid))
            return
        # FIXME add height map
        x, y, z, pitch, yaw = make_pose(
            self.sl, self.sl, loc=data.get("loc"), pitchyaw=data.get("pitchyaw")
        )
        entityId = data.get("entityId") or int(np.random.randint(0, 100000000))
        # FIXME
        name = data.get("name", "anonymous")
        p = Player(entityId, name, Pos(int(x), int(y), int(z)), Look(float(yaw), float(pitch)))
        self.players[entityId] = p
        self.connected_sids[sid] = entityId

    def setup_server(self, port=25565):
        import socketio
        import eventlet

        server = socketio.Server(async_mode="eventlet")
        self.connected_sids = {}

        @server.event
        def connect(sid, environ):
            print("connect ", sid)

        @server.event
        def disconnect(sid):
            print("disconnect ", sid)

        # the player init is separate bc connect special format, FIXME?
        @server.on("init_player")
        def init_player_event(sid, data):
            self.connect_player(sid, data)

        @server.on("line_of_sight")
        def los_event(sid, data):
            if data.get("pos"):
                pos = self.get_line_of_sight(data["pos"], data["yaw"], data["pitch"])
            else:
                if data.get("entityId"):
                    eid = data["entityId"]
                else:
                    eid = self.connected_sids.get(sid)
                if not eid:
                    raise Exception(
                        "player connected, asking for line of sight, but sid does not match any entityId"
                    )
                player_struct = self.get_player_info(eid)
                pos = self.get_line_of_sight(player_struct.pos, *player_struct.look)
            pos = pos or ""
            return {"pos": pos}

        @server.on("set_look")
        def set_agent_look(sid, data):
            eid = self.connected_sids.get(sid)
            player_struct = self.get_player_info(eid)
            # warning: it is assumed that if a player is using the sio event to set look,
            # the only thing stored here is a Player struct, not some more complicated object
            new_look = Look(data["yaw"], data["pitch"])
            self.players[entityId] = self.players[entityId]._replace(look=new_look)

        @server.on("get_player")
        def get_player_by_sid(sid):
            eid = self.connected_sids.get(sid)
            return self.get_player_info(eid)

        app = socketio.WSGIApp(server)
        eventlet.wsgi.server(eventlet.listen(("", port)), app)


if __name__ == "__main__":

    class Opt:
        pass

    spec = {"players": [], "mobs": [], "item_stacks": [], "coord_shift": (0, 0, 0), "agent": {}}
    world_opts = Opt()
    world_opts.sl = 32
    world_opts.world_server = True
    world_opts.port = 6000
    world = World(world_opts, spec)
