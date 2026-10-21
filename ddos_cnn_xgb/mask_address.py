"""
Split dataset into windows of fixed length and randomly change IP and MAC addresses (consistent within a window,
different for different windows)
"""
import numpy as np
import h5py

infile = "tf_dataset/tf_dataset_pckt.h5"
outfile = "tf_dataset/dataset_masked.h5"
window = 100
pckt_len = 64



with h5py.File(infile, 'r') as hdf5_file:
    new_add = np.random.permutation(np.arange(0,256))
    X = hdf5_file['X'][:]
    y = hdf5_file['y'][:]
    Xa = [X[i:i+window, :pckt_len] for i in range(0, len(X), window)]
    Xa = np.array(Xa[:-1])
    ya = [y[i:i+window] for i in range(0, len(y), window)]
    ya = np.array(ya[:-1])

    for i in range(Xa.shape[0]):
        new_add = np.random.permutation(np.arange(0, 256))
        for j in range(Xa.shape[1]):
            for k in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 26, 27, 28, 29, 30, 31, 32, 33):
                Xa[i, j, k] = new_add[Xa[i, j, k]]
        #ax[1].imshow(Xa[i, :, :40])
        #plt.show()
    h5f = h5py.File(outfile, "w")
    h5f.create_dataset("X", data=Xa)
    h5f.create_dataset("y", data=ya)
    h5f.close()


