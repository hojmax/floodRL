import torch
import numpy as np
import random
from PaddedEnv import PaddedEnv
from MPSPEnv import Env
from Buffer import ReplayBuffer
from multiprocessing.connection import Connection
from multiprocessing import Queue
from EpisodePlayer import EpisodePlayer


class PortCurriculum:
    def __init__(self, min, max, increment, step_size) -> None:
        self.N = min
        self._end = max
        self._increment = increment
        self._step_size = step_size
        self._count = 0

    def step(self):
        self._count += 1

        if self._count % self._step_size == 0:
            self.N = min(self.N + self._increment, self._end)


class InferenceProcess:
    def __init__(
        self,
        seed: int,
        buffer: ReplayBuffer,
        conn: Connection,
        log_episode_queue: Queue,
        config: dict,
    ) -> None:
        torch.manual_seed(seed)
        np.random.seed(seed)
        self.buffer = buffer
        self.seed = seed
        self.conn = conn
        self.log_episode_queue = log_episode_queue
        self.config = config
        self.port_curriculum = PortCurriculum(
            config["env"]["min_N"],
            config["env"]["max_N"],
            config["port_curriculum"]["increment"],
            config["port_curriculum"]["episode_step_size"],
        )

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
            self.port_curriculum.step()
            env.close()

    def _get_env(self) -> Env:
        env = PaddedEnv(
            R=random.choice(
                range(self.config["env"]["min_R"], self.config["env"]["max_R"] + 1, 2)
            ),
            C=random.choice(
                range(self.config["env"]["min_C"], self.config["env"]["max_C"] + 1, 2)
            ),
            N=random.choice(
                range(self.config["env"]["min_N"], self.port_curriculum.N + 1, 2)
            ),
            max_C=self.config["env"]["max_C"],
            max_R=self.config["env"]["max_R"],
            max_N=self.config["env"]["max_N"],
            auto_move=True,
            speedy=True,
        )
        env.reset(np.random.randint(1e9))
        return env
