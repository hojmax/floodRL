import torch
import numpy as np
from MPSPEnv import Env
from Node import Node


class MCTS:

    def __init__(
        self,
        model: torch.nn.Module,
        config: dict,
    ):
        self.model = model
        self.config = config
        self.transposition_table: dict[Env, tuple[np.ndarray, float]] = {}
        self.best_score = float("-inf")

    def run(
        self,
        root: Node,
        add_exploration_noise: bool = True,
    ) -> int:

        self.best_score = float("-inf")

        if len(root.children) == 0:
            self.best_score = self._evaluate(root)
            self._backpropagate(root, self.best_score)

        if add_exploration_noise:
            root.add_noise()

        for _ in range(self.config["mcts"]["search_iterations"]):
            node = self._find_leaf(root)
            value = self._evaluate(node)

            self._backpropagate(node, value)

            if node.env.terminal:
                self.best_score = max(self.best_score, -node.env.moves_to_solve)

        return root

    def _backpropagate(self, node: Node, value: float):
        while node.parent is not None:  # As long as not root
            node.increment_value(value)
            node = node.parent

    def _find_leaf(self, root: Node) -> Node:
        node = root

        while node.children:
            if self._should_prune(node):
                node = self._prune_and_move_back_up(node)
            else:
                node = node.select_child()

        return node

    def _should_prune(self, node: Node) -> bool:

        is_leaf = len(node.children) == 0

        too_many_reshuffles = (
            node.env.total_reward < self.best_score
            or node.env.reshuffles_per_port < -(node.env.R * node.env.C) // 2
        )

        return node.no_valid_children or (is_leaf and too_many_reshuffles)

    def _prune_and_move_back_up(self, node: Node) -> Node:
        node.prune()
        return node.parent

    def _evaluate(self, node: Node) -> float:
        if node.env.terminal:
            return -node.env.moves_to_solve
        else:
            value = self._expand_node(node)
            return value

    def _expand_node(self, node: Node) -> float:
        if node.env in self.transposition_table:
            policy, state_value = self.transposition_table[node.env]

        else:
            policy, state_value = self._run_model(node.env)

            self.transposition_table[node.env] = (policy, state_value)

        state_value -= node.depth

        self._add_children(node, policy, state_value)

        return state_value

    def _reduce_policy(self, p: np.ndarray, C: int) -> np.ndarray:
        """Hack since model produces 2 * max C policy"""
        add_policy = p[:C]
        remove_policy = p[len(p) // 2 : len(p) // 2 + C]
        return add_policy + remove_policy

    def _add_children(self, node: Node, policy: np.ndarray, state_value: float):
        policy = self._reduce_policy(policy, node.env.C)

        for action, p in enumerate(policy):
            if not node.env.mask[action]:
                continue

            node.add_child(action, node.env.copy(), p, state_value, self.config)

    def _run_model(self, env: Env) -> tuple[np.ndarray, float]:
        bay, flat_T = env.bay, env.flat_T

        bay = torch.tensor(bay)
        flat_T = torch.tensor(flat_T)
        bay = bay.unsqueeze(0).unsqueeze(0)
        flat_T = flat_T.unsqueeze(0)

        with torch.no_grad():
            policy, state_value = self.model(bay, flat_T)
            policy = policy.detach().cpu().numpy().squeeze()
            state_value = state_value.item()

        return policy, state_value