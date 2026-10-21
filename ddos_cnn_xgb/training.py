"""Train single model"""

import tensorflow as tf
import numpy as np
import h5py
from sklearn.model_selection import train_test_split
import json

infile = "tf_dataset/dataset_masked.h5"
weightfile = "tf_dataset/masked.weights.h5"
window = 100
pckt_len = 64

with h5py.File(infile, 'r') as hdf5_file:
    X = hdf5_file['X'][:]
    y = hdf5_file['y'][:]
    #Xa = [X[i:i+window, :256] for i in range(0, len(X), window)]
    #Xa = np.array(Xa[:-1])
    #ya = [max(y[i:i+window]) for i in range(0, len(y), window)]
    #ya = np.array(ya[:-1])

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.33, random_state=42)

model = tf.keras.Sequential([
    tf.keras.layers.Conv2D(
        32, (3, 3),
        activation='relu',
        input_shape=(window, pckt_len, 1)
    ),
    tf.keras.layers.MaxPooling2D(),

    tf.keras.layers.Conv2D(
        64, (3, 3),
        activation='relu'
    ),
    tf.keras.layers.MaxPooling2D(),

    tf.keras.layers.Flatten(),
    tf.keras.layers.Dense(128, activation='relu'),
    tf.keras.layers.Dense(2, activation='softmax')
])

model.compile(
    optimizer='adam',
    loss='sparse_categorical_crossentropy',
    metrics=['accuracy']
)

model.summary()

batch_size = 128
num_epochs = 10
train_dataset = tf.data.Dataset.from_tensor_slices((X_train, y_train)).batch(batch_size)
test_dataset = tf.data.Dataset.from_tensor_slices((X_test, y_test)).batch(batch_size)


model.fit(train_dataset, epochs=num_epochs, validation_data=test_dataset)
model.save_weights(weightfile)
model_json = model.to_json()
with open('model.json', 'w') as json_file:
    json_file.write(model_json)