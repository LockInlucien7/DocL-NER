# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import absolute_import
import torch
import torch.nn as nn
import numpy as np
from .charbilstm import CharBiLSTM
from .charbigru import CharBiGRU

class WordRep(nn.Module):
    def __init__(self, data):
        super(WordRep, self).__init__()
        print("build word representation...")
        self.gpu = data.HP_gpu
        self.use_char = data.use_char

        self.total_size = 0

        if self.use_char:
            self.extra_char_feature = False
            self.char_hidden_dim = data.HP_char_hidden_dim
            self.char_embedding_dim = data.char_emb_dim
            if data.char_feature_extractor == "CNN":
                from .charcnn import CharCNN
                self.char_feature = CharCNN(data.char_alphabet.size(), data.pretrain_char_embedding,
                                            self.char_embedding_dim, self.char_hidden_dim, data.HP_dropout, self.gpu)
            elif data.char_feature_extractor == "CNN3":
                from .charcnn_3k import CharCNN
                self.char_feature = CharCNN(data.char_alphabet.size(), data.pretrain_char_embedding,
                                            self.char_embedding_dim, self.char_hidden_dim, data.HP_dropout, self.gpu)
            elif data.char_feature_extractor == "LSTM":
                self.char_feature = CharBiLSTM(data.char_alphabet.size(), data.pretrain_char_embedding,
                                               self.char_embedding_dim, self.char_hidden_dim, data.HP_dropout, self.gpu)
            elif data.char_feature_extractor == "GRU":
                self.char_feature = CharBiGRU(data.char_alphabet.size(), data.pretrain_char_embedding,
                                              self.char_embedding_dim, self.char_hidden_dim, data.HP_dropout, self.gpu)
            else:
                print(
                    "Error char feature selection, please check parameter data.char_feature_extractor (CNN/LSTM/GRU).")
                exit(0)

            self.total_size += self.char_feature.char_out_size


        ## word embedding
        self.embedding_dim = data.word_emb_dim
        self.word_embedding = nn.Embedding(data.word_alphabet.size(), self.embedding_dim)
        if data.pretrain_word_embedding is not None:
            self.word_embedding.weight.data.copy_(torch.from_numpy(data.pretrain_word_embedding))
            self.word_embedding.weight.data = self.word_embedding.weight.data / self.word_embedding.weight.data.std()  # TODO
        else:
            self.word_embedding.weight.data.copy_(
                torch.from_numpy(random_embedding(data.word_alphabet.size(), self.embedding_dim)))
        self.total_size += self.embedding_dim

        ## feature embedding
        self.feature_num = data.feature_num
        self.feature_embedding_dims = data.feature_emb_dims
        self.feature_embeddings = nn.ModuleList()
        for idx in range(self.feature_num):
            self.feature_embeddings.append(
                nn.Embedding(data.feature_alphabets[idx].size(), self.feature_embedding_dims[idx]))
        for idx in range(self.feature_num):
            if data.pretrain_feature_embeddings[idx] is not None:
                self.feature_embeddings[idx].weight.data.copy_(torch.from_numpy(data.pretrain_feature_embeddings[idx]))
            else:
                self.feature_embeddings[idx].weight.data.copy_(torch.from_numpy(
                    self.random_embedding(data.feature_alphabets[idx].size(), self.feature_embedding_dims[idx])))
            self.total_size += data.feature_emb_dims[idx]

        self.drop = nn.Dropout(data.HP_dropout)
        if self.gpu:
            self.word_embedding = self.word_embedding.cuda()
            for idx in range(self.feature_num):
                self.feature_embeddings[idx] = self.feature_embeddings[idx].cuda()

    def forward(self, word_inputs, feature_inputs, word_seq_lengths, char_inputs, char_seq_lengths, char_seq_recover
                ):
        """
            input:
                word_inputs: (batch_size, sent_len)
                features: list [(batch_size, sent_len), (batch_len, sent_len),...]
                word_seq_lengths: list of batch_size, (batch_size,1)
                char_inputs: (batch_size*sent_len, word_length)
                char_seq_lengths: list of whole batch_size for char, (batch_size*sent_len, 1)
                char_seq_recover: variable which records the char order information, used to recover char order
                input_label_seq_tensor: (batch_size, number of label)
            output:
                Variable(batch_size, sent_len, hidden_dim)
        """

        batch_size = word_inputs.size(0)
        sent_len = word_inputs.size(1)
        word_embs = self.word_embedding(word_inputs)
        word_list = [word_embs]
        for idx in range(self.feature_num):
            word_list.append(self.feature_embeddings[idx](feature_inputs[idx]))
        if self.use_char:
            char_features = self.char_feature.get_last_hiddens(char_inputs, char_seq_lengths.cpu().numpy())
            char_features = char_features[char_seq_recover]
            char_features = char_features.view(batch_size, sent_len, -1)
            word_list.append(char_features)
            if self.extra_char_feature:
                char_features_extra = self.char_feature_extra.get_last_hiddens(char_inputs,
                                                                               char_seq_lengths.cpu().numpy())
                char_features_extra = char_features_extra[char_seq_recover]
                char_features_extra = char_features_extra.view(batch_size, sent_len, -1)

                word_list.append(char_features_extra)
            word_embs = torch.cat(word_list, 2)
        word_embs = self.drop(word_embs)
        return word_embs


def random_embedding(vocab_size, embedding_dim):
    pretrain_emb = np.empty([vocab_size, embedding_dim])
    scale = np.sqrt(3.0 / embedding_dim)
    for index in range(vocab_size):
        pretrain_emb[index, :] = np.random.uniform(-scale, scale, [1, embedding_dim])
    return pretrain_emb
