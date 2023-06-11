import torch
import torch.nn as nn
import torch.optim as optim
from FloodEnv import FloodEnv
from NeuralNetwork import NeuralNetwork
import Node
import numpy as np
import wandb


def loss_fn(pred_values, values, pred_probs, probs):
    value_error = torch.mean((values - pred_values) ** 2)
    cross_entropy = (
        -torch.sum(probs.flatten() * torch.log(pred_probs.flatten())) / probs.shape[0]
    )
    scaling = 0.5
    loss = scaling * value_error + cross_entropy
    return loss


def train_network(network, data, batch_size, n_batches, optimizer):
    if len(data) < batch_size:
        batch_size = len(data)

    sum_loss = 0

    for _ in range(n_batches):
        batch_indices = np.random.choice(len(data), batch_size, replace=False)
        batch = [data[i] for i in batch_indices]
        state_batch = torch.stack([x[0].squeeze(0) for x in batch])
        prob_batch = torch.stack([torch.tensor(x[1]) for x in batch])
        value_batch = torch.tensor([[x[2]] for x in batch], dtype=torch.float32)

        pred_prob_batch, pred_value_batch = network(state_batch)
        loss = loss_fn(pred_value_batch, value_batch, pred_prob_batch, prob_batch)
        optimizer.zero_grad()
        loss.backward()

        optimizer.step()

        sum_loss += loss.item()

    return sum_loss / n_batches


if __name__ == "__main__":
    all_data = []

    config = {
        "l2_weight_reg": 1e-4,
        "batch_size": 8,
        "batches_per_episode": 16,
        "learning_rate": 1e-3,
        "training_iterations": 1000,
        "width": 3,
        "height": 3,
        "n_colors": 3,
        "nn_blocks": 4,
        "c_puct": 1,
        "temperature": 0.5,
        "search_iterations": 100,
        "max_data": 1e5,
    }

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net = NeuralNetwork(
        n_colors=config["n_colors"],
        width=config["width"],
        height=config["height"],
        n_blocks=config["nn_blocks"],
    )
    net.to(device)
    optimizer = optim.Adam(
        net.parameters(),
        lr=config["learning_rate"],
        weight_decay=config["l2_weight_reg"],
    )

    wandb.init(
        entity="hojmax",
        project="bachelor",
        config=config,
    )

    for i in range(config["training_iterations"]):
        episode_data = []
        env = FloodEnv(config["width"], config["height"], config["n_colors"])
        while not env.is_terminal():
            _, probabilities = Node.alphago_zero_search(
                env,
                net,
                config["search_iterations"],
                config["c_puct"],
                config["temperature"],
            )
            episode_data.append((env.get_tensor_state(), probabilities))
            action = np.random.choice(env.n_colors, p=probabilities)
            env.step(action)

        value = env.value
        for i, (state, probabilities) in enumerate(episode_data):
            all_data.append((state, probabilities, value + i))

        if len(all_data) > config["max_data"]:
            all_data = all_data[-config["max_data"] :]

        avg_loss = train_network(
            net,
            all_data,
            config["batch_size"],
            config["batches_per_episode"],
            optimizer,
        )

        wandb.log({"loss": avg_loss, "value": value, "episode": i})

    torch.save(net.state_dict(), "model.pt")
    wandb.save("model.pt")

    wandb.finish()

    with torch.no_grad():
        for i in range(5):
            # showcase episode
            env = FloodEnv(config["width"], config["height"], config["n_colors"])
            print(env)
            while not env.is_terminal():
                _, probabilities = Node.alphago_zero_search(
                    env,
                    net,
                    config["search_iterations"],
                    config["c_puct"],
                    config["temperature"],
                )
                print("MCTS probabilities:", probabilities)
                pred_probs, pred_value = net(env.get_tensor_state())
                print("NN probabilities:", pred_probs)
                print("NN value:", pred_value)
                action = np.random.choice(env.n_colors, p=probabilities)
                env.step(action)
                print("Action:", action)
                print()
                print(env)
            print("True Value:", env.value)
            print()
