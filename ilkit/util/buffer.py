import random
import sys
from typing import Dict, Tuple, Union

import numpy as np
import torch as th

# from stable_baselines3.common.buffers import ReplayBuffer


class TransitionBuffer:
    """
    Transition buffer for single task
    """

    def __init__(
        self,
        state_shape: Tuple[int,...],
        action_shape: Tuple[int,...],
        action_dtype: Union[np.int64, np.float32],
        device: Union[str, th.device],
        buffer_size: int = -1,
    ):
        """If buffer size is not specified, it will continually add new items in without removal of old items.
        """
        self.state_shape = state_shape
        self.action_shape = action_shape
        assert action_dtype in [np.int64, np.float32], "Unsupported action dtype!"
        self.action_dtype = action_dtype  # np.int64 or np.float32
        self.device = device
        self.buffer_size = buffer_size if buffer_size != -1 else sys.maxsize
        self.clear()

    def insert_transition(
        self,
        state: np.ndarray,
        action: Union[np.ndarray, int],
        next_state: np.ndarray,
        reward: float,
        done: bool,
    ):
        # state
        state, next_state = (np.array(_, dtype=np.float32) for _ in [state, next_state])
        # action
        if self.action_dtype == np.int64:action = [action]
        action = np.array(action, dtype=self.action_dtype)
        # reward and done
        reward, done = (np.array([_], dtype=np.float32) for _ in [reward, done])
            
        new_transition = [state, action, next_state, reward, done]
        new_transition = [th.tensor(item).to(self.device) for item in new_transition]

        if self.total_size <= self.buffer_size:
            self.buffers = [
                th.cat((self.buffers[i], th.unsqueeze(new_transition[i], dim=0)), dim=0)
                for i in range(len(new_transition))
            ]
        else:
            for buffer, new_data in zip(self.buffers, new_transition):
                buffer[self.ptr] = new_data

        # update pointer and size
        self.ptr = (self.ptr + 1) % self.buffer_size
        self.size = min(self.size + 1, self.buffer_size)
        self.total_size += 1

    def insert_batch(
        self,
        states: np.ndarray,
        actions: Union[np.ndarray, int],
        next_states: np.ndarray,
        rewards: float,
        dones: bool,
    ):
        """Insert a batch of transitions
        """
        for i in range(states.shape[0]):
            self.insert_transition(
                states[i], actions[i], next_states[i], rewards[i], dones[i]
            )

    def insert_dataset(self, dataset: Dict):
        """Insert dataset into the buffer
        """
        observations, actions, next_observations, rewards, terminals = (
            dataset["observations"],
            dataset["actions"],
            dataset["next_observations"],
            dataset["rewards"],
            dataset["terminals"],
        )  # we currently not consider the log_pis. But you can insert it with small modifications
        self.insert_batch(observations, actions, next_observations, rewards, terminals)

    def sample(self, batch_size: int = None, shuffle: bool = True):
        """Randomly sample items from the buffer.
        
        If batch_size is not provided, we will sample all the stored items.
        """
        idx = list(range(self.size))
        if shuffle:
            random.shuffle(idx)
        if batch_size is not None:
            idx = idx[:batch_size]

        return [buffer[idx] for buffer in self.buffers]

    def clear(self):
        # unlike some popular implementations, we start with an empty buffer located in self.device (may be gpu)
        
        state_shape = (0,) + self.state_shape
        
        if self.action_dtype == np.int64:
            action_shape = (0, 1)
        else:
            action_shape = (0,) + self.action_shape
        
        self.buffers = [
            th.zeros(state_shape),  # state_buffer
            th.tensor(np.zeros(action_shape, dtype=self.action_dtype)),  # action_buffer
            th.zeros(state_shape),  # next_state_buffer
            th.zeros((0, 1)),  # reward_buffer
            th.zeros((0, 1)),  # done_buffer
        ]
        self.buffers = [item.to(self.device) for item in self.buffers]
        self.ptr = 0
        self.size = 0
        self.total_size = 0  # Number of all the pushed items


class DAggerBuffer:
    """
    Transition buffer for DAgger
    """

    def __init__(
        self,
        state_shape: Tuple[int,...],
        action_shape: Tuple[int,...],
        action_dtype: Union[np.int64, np.float32],
        device: Union[str, th.device],
        buffer_size: int = -1,
    ):
        """If buffer size is not specified, this buffer will continually add new items in without removal of old items.
        """
        self.state_shape = state_shape
        self.action_shape = action_shape
        assert action_dtype in [np.int64, np.float32], "Unsupported action dtype!"
        self.action_dtype = action_dtype
        self.device = device
        self.buffer_size = buffer_size if buffer_size != -1 else sys.maxsize
        self.clear()

    def insert_transition(self, state: np.ndarray, action: Union[np.ndarray, int]):

        state = np.array(state, dtype=np.float32)

        if self.action_dtype == np.int64: action = [action]
        action = np.array(action, dtype=self.action_dtype)

        new_transition = [state, action]
        new_transition = [th.tensor(item).to(self.device) for item in new_transition]

        if self.total_size <= self.buffer_size:
            self.buffers = [
                th.cat((self.buffers[i], th.unsqueeze(new_transition[i], dim=0)), dim=0)
                for i in range(len(new_transition))
            ]
        else:
            for buffer, new_data in zip(self.buffers, new_transition):
                buffer[self.ptr] = new_data

        # update pointer and size
        self.ptr = (self.ptr + 1) % self.buffer_size
        self.size = min(self.size + 1, self.buffer_size)
        self.total_size += 1

    def insert_batch(self, states: np.ndarray, actions: Union[np.ndarray, int]):
        """Insert a batch of transitions
        """
        for i in range(states.shape[0]):
            self.insert_transition(states[i], actions[i])

    def sample(self, batch_size: int = None, shuffle: bool = True):
        """Randomly sample items from the buffer.
        
        If batch_size is not provided, we will sample all the stored items.
        """
        idx = list(range(self.size))
        if shuffle:
            random.shuffle(idx)
        if batch_size is not None:
            idx = idx[:batch_size]

        return [buffer[idx] for buffer in self.buffers]

    def clear(self):
        # unlike some popular implementations, we start with an empty buffer located in self.device (may be gpu)
        state_shape = (0,) + self.state_shape
        if self.action_dtype == np.int64:
            action_shape = (0, 1)
        else:
            action_shape = (0,) + self.action_shape
        
        self.buffers = [
            th.zeros(state_shape),  # state_buffer
            th.tensor(np.zeros(action_shape, dtype=self.action_dtype)),  # action_buffer
        ]
        self.buffers = [item.to(self.device) for item in self.buffers]
        
        self.ptr = 0
        self.size = 0
        self.total_size = 0  # Number of all the pushed items
