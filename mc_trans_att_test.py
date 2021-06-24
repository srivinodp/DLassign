# -*- coding: utf-8 -*-
"""A4_T4test.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1d4vJNSOF6zeeoi44__vX7rn92PQLa2Gx
"""

import tensorflow as tf
import numpy as np
import tensorflow_datasets as tfds
from keras.preprocessing.text import Tokenizer


import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from sklearn.model_selection import train_test_split

import unicodedata
import re
import numpy as np
import os
import io
import time

from google.colab import drive
drive.mount('/content/drive')

embeddings_index = dict()
f = open('/content/drive/My Drive/glove.6B.300d.txt',encoding="utf-8")
for line in f:
    values = line.split()
    word = values[0]
    coefs = np.asarray(values[1:], dtype='float32')
    embeddings_index[word] = coefs
f.close()
print('Loaded %s word vectors.' % len(embeddings_index))

docs=embeddings_index.keys()
tokenizer_en = Tokenizer(num_words=400000)
tokenizer_en.fit_on_texts(docs)
vocab_size = len(tokenizer_en.word_index) + 3
embedding_matrix = np.zeros((vocab_size, 300))
for word, i in tokenizer_en.word_index.items():
    embedding_vector = embeddings_index.get(word)
    if embedding_vector is not None:
        embedding_matrix[i] = embedding_vector

train_dataset_en=tf.data.TextLineDataset('/content/drive/My Drive/train.en')
train_dataset_ta=tf.data.TextLineDataset('/content/drive/My Drive/train.ta')
train_dataset_en=[str(i.decode('utf-8')).replace('\'',' \'') for i in train_dataset_en.as_numpy_iterator()]
train_dataset_en=tf.data.Dataset.from_tensor_slices(train_dataset_en)

# print(train_dataset_en.shape)

#tokenizer_ta= tfds.features.text.SubwordTextEncoder.build_from_corpus((element for element in train_dataset_ta.as_numpy_iterator()), target_vocab_size=10000)
#subword - vocab_size
tokenizer_ta=tf.keras.preprocessing.text.Tokenizer(num_words=400000,oov_token='oov')
texts=[str(i.decode('utf-8'))for i in train_dataset_ta.as_numpy_iterator()]

tokenizer_ta.fit_on_texts(texts)

vocab_size = len(tokenizer_en.word_index) + 3
# vocab_tar_size = tokenizer_ta.vocab_size + 3
vocab_tar_size = len(tokenizer_ta.word_index) + 3
units = 1024
BATCH_SIZE = 64
embedding_dim = 256

class Encoder(tf.keras.Model):
  def __init__(self, vocab_size, embedding_matrix, enc_units, batch_sz):
    super(Encoder, self).__init__()
    self.batch_sz = batch_sz
    self.enc_units = enc_units
    self.embedding = tf.keras.layers.Embedding(vocab_size, 300,embeddings_initializer=tf.keras.initializers.Constant(embedding_matrix),trainable=False)
    self.lstm = tf.keras.layers.LSTM(self.enc_units,
                                   return_sequences=True,
                                   return_state=True,
                                   recurrent_initializer='glorot_uniform')

  def call(self, x, hidden):
    x = self.embedding(x)
    output, state, cell = self.lstm(x, initial_state = hidden)
    return output, state, cell

  def initialize_hidden_state(self):
    return tf.zeros((self.batch_sz, self.enc_units))

class BahdanauAttention(tf.keras.layers.Layer):
  def __init__(self, units):
    super(BahdanauAttention, self).__init__()
    self.W1 = tf.keras.layers.Dense(units)
    self.W2 = tf.keras.layers.Dense(units)
    self.V = tf.keras.layers.Dense(1)

  def call(self, query, values):
    query_with_time_axis = tf.expand_dims(query, 1)

    score = self.V(tf.nn.tanh(
        self.W1(query_with_time_axis) + self.W2(values)))

    # attention_weights shape == (batch_size, max_length, 1)
    attention_weights = tf.nn.softmax(score, axis=1)

    # context_vector shape after sum == (batch_size, hidden_size)
    context_vector = attention_weights * values
    context_vector = tf.reduce_sum(context_vector, axis=1)

    return context_vector, attention_weights

class Decoder(tf.keras.Model):
  def __init__(self, vocab_size, embedding_dim, dec_units, batch_sz):
    super(Decoder, self).__init__()
    self.batch_sz = batch_sz
    self.dec_units = dec_units
    self.embedding = tf.keras.layers.Embedding(vocab_size, embedding_dim)
    self.lstm = tf.keras.layers.LSTM(self.dec_units,
                                   return_sequences=True,
                                   return_state=True,
                                   recurrent_initializer='glorot_uniform')
    self.fc = tf.keras.layers.Dense(vocab_size)

    # used for attention
    self.attention = BahdanauAttention(self.dec_units)

  def call(self, x, hidden, enc_output):
    # enc_output shape == (batch_size, max_length, hidden_size)
    context_vector, attention_weights = self.attention(hidden[0], enc_output)

    # x shape after passing through embedding == (batch_size, 1, embedding_dim)
    x = self.embedding(x)

    # x shape after concatenation == (batch_size, 1, embedding_dim + hidden_size)
    x = tf.concat([tf.expand_dims(context_vector, 1), x], axis=-1)

    # passing the concatenated vector to the GRU
    output, state, cell = self.lstm(x,initial_state = hidden)

    # output shape == (batch_size * 1, hidden_size)
    output = tf.reshape(output, (-1, output.shape[2]))

    # output shape == (batch_size, vocab)
    x = self.fc(output)

    return x, state, attention_weights

encoder = Encoder(vocab_size, embedding_matrix, units, BATCH_SIZE)
sample_hidden = [encoder.initialize_hidden_state(),encoder.initialize_hidden_state()]
sample_output, sample_hidden,sample_cell = encoder(tf.zeros((BATCH_SIZE,1)),sample_hidden)
encoder.load_weights('/content/drive/My Drive/encoder_last_attention.h5')

decoder = Decoder(vocab_tar_size, embedding_dim, units, BATCH_SIZE)
sample_hidden = [encoder.initialize_hidden_state(),encoder.initialize_hidden_state()]
sample_decoder_output, _, _ = decoder(tf.random.uniform((BATCH_SIZE, 1)),
                                      sample_hidden, sample_output)
decoder.load_weights('/content/drive/My Drive/decoder_last_attention.h5')

def evaluate(sentence,max_length_targ=100):
#   attention_plot = np.zeros((max_length_targ, max_length_inp))

  start_token = [len(tokenizer_en.word_index)+1]
  end_token = [len(tokenizer_en.word_index) + 2]
  
  st=tokenizer_en.texts_to_sequences([sentence.lower()])
  flat_list = [item for sublist in st for item in sublist]
  inp_sentence = start_token + flat_list + end_token
  encoder_input = tf.expand_dims(inp_sentence, 0)
  
  result = []

  hidden = [tf.zeros((1, units))]
  enc_out, enc_hidden = encoder(encoder_input, hidden)

  dec_hidden = enc_hidden
#   dec_input = tf.expand_dims([tokenizer_ta.vocab_size+1] , 0)
  dec_input = tf.expand_dims([len(tokenizer_ta.word_index)+1] , 0)


  for t in range(max_length_targ):
    predictions, dec_hidden,_ = decoder(dec_input,
                                                         dec_hidden,
                                                         enc_out)

    # storing the attention weights to plot later on
    # attention_weights = tf.reshape(attention_weights, (-1, ))
    # attention_plot[t] = attention_weights.numpy()

    predicted_id = tf.argmax(predictions[0]).numpy()

    
    result += [predicted_id]
    
    if predicted_id == len(tokenizer_ta.word_index)+2:
      return result, sentence
    
    
    # the predicted ID is fed back into the model
    dec_input = tf.expand_dims([predicted_id], 0)

  return result, sentence

def translate(sentence):
  result,sent = evaluate(sentence)
  
  predicted_sentence = tokenizer_ta.sequences_to_texts([result[:-1]])  

  print('Input: {}'.format(sentence))
  return predicted_sentence[0]

prediction=translate("You gotta get me to Charleston.".replace('\'',' \''))
print(prediction)
print ("நான் ஞாயிறுகளில் அவளை நாம் மற்ற கூறினார்.")

print(translate("That's where we're going."))
print ("நாம் எங்கே போகிறோம் என்று.")

test_dataset_en=tf.data.TextLineDataset('/content/drive/My Drive/nmt_test.en')
test_dataset_ta=tf.data.TextLineDataset('/content/drive/My Drive/nmt_test.ta')

test_dataset_en=[str(i.decode('utf-8')).replace('\'',' \'') for i in test_dataset_en.as_numpy_iterator()]
test_dataset_en=tf.data.Dataset.from_tensor_slices(test_dataset_en)

test_dataset = tf.data.Dataset.zip((test_dataset_en, test_dataset_ta))

from nltk.translate.bleu_score import sentence_bleu
def bleu_score_function(reference,candidate):
  bleu1=sentence_bleu([reference], candidate,weights=(1, 0, 0, 0))
  bleu2=sentence_bleu([reference], candidate,weights=(0.5, 0.5, 0, 0))
  bleu3=sentence_bleu([reference], candidate,weights=(0.33, 0.33, 0.33, 0))
  bleu4=sentence_bleu([reference], candidate,weights=(0.25, 0.25, 0.25, 0.25))
  return bleu1,bleu2,bleu3,bleu4

scores1=[]
scores2=[]
scores3=[]
scores4=[]
for(inp,tar) in test_dataset:
  prediction=translate(inp.numpy().decode('utf-8').lower().replace('\'',' \''))
  print(inp.numpy())
  reference=tar.numpy().decode('utf-8').split(' ')
  candidate=prediction.split(' ')
  print(reference)
  print(candidate)
  bleu1,bleu2,bleu3,bleu4 = bleu_score_function(reference, candidate)
  print(bleu1)
  print(bleu2)
  print(bleu3)
  print(bleu4)
  scores1.append(bleu1)
  scores2.append(bleu2)
  scores3.append(bleu3)
  scores4.append(bleu4)
  break


print(sum(scores1)/len(scores1))
print(sum(scores2)/len(scores2))
print(sum(scores3)/len(scores3))
print(sum(scores4)/len(scores4))