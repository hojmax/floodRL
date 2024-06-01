import torch
import numpy as np
import random
from PaddedEnv import PaddedEnv
from MPSPEnv import Env
from Buffer import ReplayBuffer
from multiprocessing.connection import Connection
from multiprocessing import Queue
from EpisodePlayer import EpisodePlayer
import torch.multiprocessing as mp


class InferenceProcess:
    def __init__(
        self,
        seed: int,
        buffer: ReplayBuffer,
        conn: Connection,
        log_episode_queue: Queue,
        config: dict,
        current_env_size: mp.Array,
    ) -> None:
        torch.manual_seed(seed)
        np.random.seed(seed)
        self.buffer = buffer
        self.seed = seed
        self.conn = conn
        self.log_episode_queue = log_episode_queue
        self.config = config
        self.current_env_size = current_env_size

    def loop(self):
        while True:
            env = self._get_env()

            player = EpisodePlayer(env, self.conn, self.config, deterministic=False)
            (
                observations,
                value,
                reshuffles,
                remove_fraction,
            ) = player.run_episode()

            self.buffer.extend(observations)

            self.log_episode_queue.put(
                {
                    "value": value,
                    "reshuffles": reshuffles,
                    "remove_fraction": remove_fraction,
                    "n_observations": len(observations),
                    "tag": f"R{env.R}C{env.C}N{env.N}",
                }
            )
            env.close()

    def _get_env(self) -> Env:
        env = PaddedEnv(
            R=self.current_env_size[0],
            C=self.current_env_size[1],
            N=self.current_env_size[2],
            max_C=self.config["env"]["C"],
            max_R=self.config["env"]["R"],
            max_N=self.config["env"]["N"],
            auto_move=True,
            speedy=True,
        )
        env.reset(np.random.randint(1e9))
        return env
