from pyprind import ProgPercent
import numpy as np
import click
import json

from abstract_rbm import AbstractRBM
import util


class RBM(AbstractRBM):

    """Restricted Boltzmann Machine implementation with
    visible and hidden Bernoulli units.
    """

    def __init__(self, num_visible, num_hidden,
                 W=None, h_bias=None, v_bias=None):

        self.num_visible = num_visible
        self.num_hidden = num_hidden

        if W is None and any([h_bias, v_bias]) is None:
            raise Exception('If W is None, then also b and c must be None')

        if W is None:
            # Initialize the weight matrix, using
            # a Gaussian ddistribution with mean 0 and standard deviation 0.1
            self.W = 0.1 * np.random.randn(self.num_visible, self.num_hidden)
            self.h_bias = np.ones(self.num_hidden)
            self.v_bias = np.ones(self.num_visible)
        else:
            self.W = W
            self.h_bias = h_bias
            self.v_bias = v_bias
        # debugging values
        self.costs = []
        self.train_free_energies = []
        self.validation_free_energies = []
        # last gradient, used for momentum
        self.last_velocity = 0.0

    def train(self, data, validation=None, max_epochs=100, batch_size=10,
              alpha=0.1, m=0.5, gibbs_k=1, verbose=False, display=None):
        """Train the restricted boltzmann machine with the given parameters.

        :param data: the training set

        :param validation: the validation set

        :param max_epochs: number of training steps

        :param batch_size: size of each batch

        :param alpha: learning rate

        :param m: momentum parameter

        :param gibbs_k: mumber of gibbs sampling steps

        :param verbose: if true display a progress bar through the loop

        :param display: function used to display reconstructed samples
                        after gibbs sampling for each epoch.
                        If batch_size is greater than one, one
                        random sample will be displayed.

        """
        # Initialize total error
        total_error = 0

        # Set the visible bias weights to the approximate probability
        # of a neuron being activated in the training data.
        # This is the logarithm of the 1 / (1 - neuron_mean), where neuron_mean
        # is the proportion of training vectors in which unit i is
        neuron_mean = data.mean(axis=0)
        for i in xrange(neuron_mean.shape[0]):
            if neuron_mean[i] == 1:
                neuron_mean[i] = 0.99999
        neuron_mean = 1 / (1 - neuron_mean)
        self.v_bias = np.log(neuron_mean)

        # divide data into batches
        batches = util.generate_batches(data, batch_size)
        # Learning rate update rule
        alpha_update = int(max_epochs / (alpha / 0.01)) + 1
        # Momentum parameter update rule
        m_update = int(max_epochs / ((0.9 - m) / 0.01)) + 1

        for epoch in xrange(max_epochs):
            if verbose:
                prog_bar = ProgPercent(len(batches))
            for batch in batches:
                if verbose:
                    prog_bar.update()
                (associations_delta, h_bias_delta, v_probs_new,
                 h_probs_new) = self.gibbs_sampling(batch, gibbs_k)
                # useful to compute the error
                v_states = (v_probs_new > np.random.rand(
                    batch_size, self.num_visible)).astype(np.int)

                # weights update
                deltaW = alpha * \
                    (associations_delta / float(batch_size)) + \
                    m*self.last_velocity
                self.W += deltaW
                self.last_velocity = deltaW
                # bias updates mean through the batch
                self.h_bias += alpha * (h_bias_delta).mean(axis=0)
                self.v_bias += alpha * \
                    (batch - v_probs_new).mean(axis=0)

                error = np.sum((batch - v_probs_new) ** 2) / float(batch_size)
                total_error += error

            if display and verbose:
                print("Reconstructed sample from the training set")
                print display(v_states[np.random.randint(v_states.shape[0])])

            print("Epoch %s : error is %s" % (epoch, total_error))
            if epoch % 25 == 0 and epoch > 0:
                self.train_free_energies.append(
                    self.average_free_energy(batches[0]))
                if validation is not None:
                    self.validation_free_energies.append(
                        self.average_free_energy(validation))
            if epoch % m_update == 0 and epoch > 0:
                m += 0.01
            if epoch % alpha_update == 0 and epoch > 0 and alpha > 0.01:
                alpha -= 0.01
            self.costs.append(total_error)
            total_error = 0

    def gibbs_sampling(self, v_in_0, k):
        """Performs k steps of Gibbs Sampling, starting from the visible units input.

        :param v_in_0: input of the visible units

        :param k: number of sampling steps

        :return difference between positive associations and negative
        associations after k steps of gibbs sampling

        """
        batch_size = v_in_0.shape[0]

        # Sample from the hidden units given the visible units - Positive
        # Constrastive Divergence phase
        h_activations_0 = np.dot(v_in_0, self.W) + self.h_bias
        h_probs_0 = self.hidden_act_func(h_activations_0)
        h_states_0 = (h_probs_0 > np.random.rand(
            batch_size, self.num_hidden)).astype(np.int)
        pos_associations = np.dot(v_in_0.T, h_states_0)

        for gibbs_step in xrange(k):
            if gibbs_step == 0:
                # first step: we have already computed the hidden things
                h_activations = h_activations_0
                h_probs = h_probs_0
                h_states = h_states_0
            else:
                # Not first step: sample hidden from new visible
                # Sample from the hidden units given the visible units -
                # Positive CD phase
                h_activations = np.dot(v_in_0, self.W) + self.h_bias
                h_probs = self.hidden_act_func(h_activations)
                h_states = (
                    h_probs > np.random.rand(batch_size, self.num_hidden)
                ).astype(np.int)

            # Reconstruct the visible units
            # units - Negative Contrastive Divergence phase
            v_activations = np.dot(h_states, self.W.T) + self.v_bias
            v_probs = self.visible_act_func(v_activations)
            # Sampling again from the hidden units
            h_activations_new = np.dot(v_probs, self.W) + self.h_bias
            h_probs_new = self.hidden_act_func(h_activations_new)
            h_states_new = (
                h_probs_new > np.random.rand(batch_size, self.num_hidden)
            ).astype(np.int)
            # We are again using states but we could have used probabilities
            neg_associations = np.dot(v_probs.T, h_states_new)
            # Use the new sampled visible units in the next step
            v_in_0 = v_probs
        return (pos_associations - neg_associations,
                h_probs_0 - h_probs_new,
                v_probs,
                h_probs_new)

    def sample_visible_from_hidden(self, h_in, gibbs_k=1):
        """
        Assuming the RBM has been trained, run the network on a set of
        hidden units, to get a sample of the visible units.

        :param h_in: states of the hidden units.

        :param gibbs_k: mumber of gibbs sampling steps

        :return (visible units probabilities, visible units states)

        """
        (_, _, v_probs, _) = self.gibbs_sampling(h_in, gibbs_k)
        v_states = (v_probs > np.random.rand(v_probs.shape[0], v_probs.shape[1])).astype(np.int)
        return (v_probs, v_states)

    def sample_hidden_from_visible(self, v_in, gibbs_k=1):
        """
        Assuming the RBM has been trained, run the network on a set of
        visible units, to get a sample of the visible units.

        :param v_in: states of the visible units.

        :param gibbs_k: mumber of gibbs sampling steps

        :return (hidden units probabilities, hidden units states)

        """
        (_, _, _, h_probs) = self.gibbs_sampling(v_in, gibbs_k)
        h_states = (h_probs > np.random.rand(h_probs.shape[0], h_probs.shape[1])).astype(np.int)
        return (h_probs, h_states)

    def visible_act_func(self, x):
        """Sigmoid function"""
        return 1.0 / (1 + np.exp(-x))

    def hidden_act_func(self, x):
        """Sigmoid function"""
        return 1.0 / (1 + np.exp(-x))

    def average_free_energy(self, data):
        """Compute the average free energy over a representative sample
        of the training set or the validation set.
        """
        wx_b = np.dot(data, self.W) + self.h_bias
        vbias_term = np.dot(data, self.v_bias)
        hidden_term = np.sum(np.log(1 + np.exp(wx_b)), axis=1)
        return (- hidden_term - vbias_term).mean(axis=0)

    def save_configuration(self, outfile):
        """Save a json representation of the RBM object.

        :param outfile: path of the output file

        """
        with open(outfile, 'w') as f:
            f.write(json.dumps({'W': self.W.tolist(),
                                'h_bias': self.h_bias.tolist(),
                                'v_bias': self.v_bias.tolist(),
                                'num_hidden': self.num_hidden,
                                'num_visible': self.num_visible,
                                'costs': self.costs,
                                'train_free_energies':
                                    self.train_free_energies,
                                'validation_free_energies':
                                    self.validation_free_energies}))

    def load_configuration(self, infile):
        """Load a json representation of the RBM object.

        :param infile: path of the input file

        """
        with open(infile, 'r') as f:
            data = json.load(f)
            self.W = np.array(data['W'])
            self.h_bias = np.array(data['h_bias'])
            self.v_bias = np.array(data['v_bias'])
            self.num_hidden = data['num_hidden']
            self.num_visible = data['num_visible']
            self.costs = data['costs']
            self.train_free_energies = data['train_free_energies']
            self.validation_free_energies = data['validation_free_energies']


@click.command()
@click.option('--config', default='', help='json with the config of the rbm')
def main(config):
    with open(config, 'r') as f:
        data = json.load(f)
        num_visible = data['num_visible']
        num_hidden = data['num_hidden']
        act_func = data['act_func']
        dataset = np.array(data['dataset'])
        max_epochs = data['max_epochs']
        alpha = data['alpha']
        m = data['m']
        batch_size = data['batch_size']
        gibbs_k = data['gibbs_k']
        verbose = data['verbose']
        out = data['outfile']
        # create rbm object
        rbm = RBM(num_visible, num_hidden, act_func)
        rbm.train(dataset,
                  max_epochs=max_epochs,
                  alpha=alpha,
                  m=m,
                  batch_size=batch_size,
                  gibbs_k=gibbs_k,
                  verbose=verbose)
        rbm.save_configuration(out)


if __name__ == '__main__':
    main()
