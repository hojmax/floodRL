import torch
import torch.nn as nn


class Convolutional_Block(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, stride):
        super().__init__()
        self.conv1 = nn.Conv2d(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=kernel_size,
            stride=stride,
            padding="same",
        )
        self.silu = nn.SiLU()
        self.batch = nn.BatchNorm2d(out_channels)

    def forward(self, x):
        out = self.conv1(x)
        out = self.batch(out)
        out = self.silu(out)
        return out


class Residual_Block(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, stride):
        super().__init__()
        self.conv1 = nn.Conv2d(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=kernel_size,
            stride=stride,
            padding="same",
        )
        self.conv2 = nn.Conv2d(
            in_channels=out_channels,
            out_channels=out_channels,
            kernel_size=kernel_size,
            stride=stride,
            padding="same",
        )
        self.silu = nn.SiLU()
        self.batch1 = nn.BatchNorm2d(out_channels)
        self.batch2 = nn.BatchNorm2d(out_channels)

    def forward(self, x):
        out = self.conv1(x)
        out = self.batch1(out)
        out = self.silu(out)
        out = self.conv2(out)
        out = self.batch2(out)
        out = out + x
        out = self.silu(out)
        return out


def dict_to_cpu(dictionary):
    cpu_dict = {}
    for key, value in dictionary.items():
        if isinstance(value, torch.Tensor):
            cpu_dict[key] = value.cpu()
        elif isinstance(value, dict):
            cpu_dict[key] = dict_to_cpu(value)
        else:
            cpu_dict[key] = value
    return cpu_dict


class NeuralNetwork(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.env_config = config["env"]
        nn_config = config["nn"]
        input_channels = 2

        layers = []
        layers.append(
            Convolutional_Block(
                input_channels,
                nn_config["hidden_channels"],
                nn_config["hidden_kernel_size"],
                stride=nn_config["hidden_stride"],
            )
        )
        for _ in range(nn_config["blocks"]):
            layers.append(
                Residual_Block(
                    nn_config["hidden_channels"],
                    nn_config["hidden_channels"],
                    nn_config["hidden_kernel_size"],
                    nn_config["hidden_stride"],
                )
            )

        self.layers = nn.Sequential(*layers)

        self.flat_T_reshaper = nn.Sequential(
            nn.Linear(
                self.env_config["N"] * (self.env_config["N"] - 1) // 2,
                self.env_config["R"] * self.env_config["C"],
            ),
            nn.Sigmoid(),
        )

        self.policy_head = nn.Sequential(
            nn.Conv2d(
                in_channels=nn_config["hidden_channels"],
                out_channels=nn_config["policy_channels"],
                kernel_size=nn_config["policy_kernel_size"],
                stride=nn_config["policy_stride"],
            ),
            nn.BatchNorm2d(nn_config["policy_channels"]),
            nn.SiLU(),
            nn.Flatten(),
            nn.Linear(
                nn_config["policy_channels"]
                * self.env_config["R"]
                * self.env_config["C"],
                2 * self.env_config["C"],
            ),
            nn.Softmax(dim=1),
        )

        self.value_head = nn.Sequential(
            nn.Conv2d(
                in_channels=nn_config["hidden_channels"],
                out_channels=nn_config["value_channels"],
                kernel_size=nn_config["value_kernel_size"],
                stride=nn_config["value_stride"],
            ),
            nn.BatchNorm2d(nn_config["value_channels"]),
            nn.SiLU(),
            nn.Flatten(),
            nn.Linear(
                nn_config["value_channels"]
                * self.env_config["R"]
                * self.env_config["C"],
                nn_config["value_hidden"],
            ),
            nn.SiLU(),
            nn.Linear(nn_config["value_hidden"], 1),
        )

    def forward(self, bay, flat_T):

        flat_T = self.flat_T_reshaper(flat_T)
        flat_T = flat_T.view(-1, 1, self.env_config["R"], self.env_config["C"])
        try:
            x = torch.cat([bay, flat_T], dim=1)
        except:
            print(bay.shape, flat_T.shape)
            raise
        out = self.layers(x)
        policy = self.policy_head(out)
        value = self.value_head(out)
        return policy, value

    def get_weights(self):
        return dict_to_cpu(self.state_dict())

    def set_weights(self, weights):
        self.load_state_dict(weights)
