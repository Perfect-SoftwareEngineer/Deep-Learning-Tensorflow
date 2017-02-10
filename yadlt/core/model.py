"""Model scheleton."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import tensorflow as tf

from .config import Config


class Model(object):
    """Class representing an abstract Model."""

    def __init__(self, name):
        """Constructor.

        :param name: name of the model, used as filename.
            string, default 'dae'
        """
        self.name = name
        self.model_path = os.path.join(Config().models_dir, self.name)

        self.input_data = None
        self.input_labels = None
        self.keep_prob = None
        self.layer_nodes = []  # list of layers of the final network
        self.last_out = None
        self.train_step = None
        self.cost = None
        self.verbose = 0

        # tensorflow objects
        self.tf_graph = tf.Graph()
        self.tf_session = None
        self.tf_saver = None
        self.tf_merged_summaries = None
        self.tf_summary_writer = None
        self.tf_summary_writer_available = True

    def _initialize_tf_utilities_and_ops(self, restore_previous_model):
        """Initialize TensorFlow operations.

        tf operations: summaries, init operations, saver, summary_writer.
        Restore a previously trained model if the flag restore_previous_model
            is true.
        :param restore_previous_model:
                    if true, a previous trained model
                    with the same name of this model is restored from disk
                    to continue training.
        """
        self.tf_merged_summaries = tf.summary.merge_all()
        init_op = tf.global_variables_initializer()
        self.tf_saver = tf.train.Saver()

        self.tf_session.run(init_op)

        if restore_previous_model:
            self.tf_saver.restore(self.tf_session, self.model_path)

        # Retrieve run identifier
        run_id = 0
        for e in os.listdir(Config().logs_dir):
            if e[:3] == 'run':
                r = int(e[3:])
                if r > run_id:
                    run_id = r
        run_id += 1
        run_dir = os.path.join(Config().logs_dir, 'run' + str(run_id))
        print('Tensorboard logs dir for this run is %s' % (run_dir))

        self.tf_summary_writer = tf.summary.FileWriter(
            run_dir, self.tf_session.graph)

    def _initialize_training_parameters(
        self, loss_func, learning_rate, num_epochs, batch_size,
        opt='sgd', dropout=1, momentum=None, regtype='none',
            l2reg=None):
        """Initialize training parameters common to all models.

        :param loss_func: Loss function. ['mean_squared', 'cross_entropy']
        :param learning_rate: Initial learning rate
        :param num_epochs: Number of epochs
        :param batch_size: Size of each mini-batch
        :param opt: Which tensorflow optimizer to use.
            ['sgd', 'momentum', 'ada_grad']
        :param dropout: Dropout parameter
        :param momentum: Momentum parameter
        :param l2reg: regularization parameter
        :return: self
        """
        self.loss_func = loss_func
        self.learning_rate = learning_rate
        self.dropout = dropout
        self.num_epochs = num_epochs
        self.batch_size = batch_size
        self.opt = opt
        self.momentum = momentum
        self.regtype = regtype
        self.l2reg = l2reg

    def compute_regularization(self, vars):
        """Compute the regularization tensor.

        :param vars: list of model variables
        :return:
        """
        if self.regtype != 'none':

            regularizers = tf.constant(0.0)

            for v in vars:
                if self.regtype == 'l2':
                    regularizers = tf.add(regularizers, tf.nn.l2_loss(v))
                elif self.regtype == 'l1':
                    regularizers = tf.add(
                        regularizers, tf.reduce_sum(tf.abs(v)))

            return tf.mul(self.l2reg, regularizers)
        else:
            return None

    def pretrain_procedure(self, layer_objs, layer_graphs, set_params_func,
                           train_set, validation_set=None):
        """Perform unsupervised pretraining of the model.

        :param layer_objs: list of model objects (autoencoders or rbms)
        :param layer_graphs: list of model tf.Graph objects
        :param set_params_func: function used to set the parameters after
            pretraining
        :param train_set: training set
        :param validation_set: validation set
        :return: return data encoded by the last layer
        """
        next_train = train_set
        next_valid = validation_set

        for l, layer_obj in enumerate(layer_objs):
            print('Training layer {}...'.format(l + 1))
            next_train, next_valid = self._pretrain_layer_and_gen_feed(
                layer_obj, set_params_func, next_train, next_valid,
                layer_graphs[l])

        return next_train, next_valid

    def _pretrain_layer_and_gen_feed(self, layer_obj, set_params_func,
                                     train_set, validation_set, graph):
        """Pretrain a single autoencoder and encode the data for the next layer.

        :param layer_obj: layer model
        :param set_params_func: function used to set the parameters after
            pretraining
        :param train_set: training set
        :param validation_set: validation set
        :param graph: tf object for the rbm
        :return: encoded train data, encoded validation data
        """
        layer_obj.fit(train_set, train_set,
                      validation_set, validation_set, graph=graph)

        with graph.as_default():
            set_params_func(layer_obj, graph)

            next_train = layer_obj.transform(train_set, graph=graph)
            if validation_set is not None:
                next_valid = layer_obj.transform(validation_set, graph=graph)
            else:
                next_valid = None

        return next_train, next_valid

    def get_layers_output(self, dataset):
        """Get output from each layer of the network.

        :param dataset: input data
        :return: list of np array, element i is the output of layer i
        """
        layers_out = []

        with self.tf_graph.as_default():
            with tf.Session() as self.tf_session:
                self.tf_saver.restore(self.tf_session, self.model_path)
                for l in self.layer_nodes:
                    layers_out.append(l.eval({self.input_data: dataset,
                                              self.keep_prob: 1}))

        if layers_out == []:
            raise Exception("This method is not implemented for this model")
        else:
            return layers_out

    def _create_last_layer(self, last_layer, n_classes):
        """Create the last layer for finetuning.

        :param last_layer: last layer output node
        :param n_classes: number of classes
        :return: self
        """
        with tf.name_scope("last_layer"):
            self.last_W = tf.Variable(
                tf.truncated_normal(
                    [last_layer.get_shape()[1].value, n_classes], stddev=0.1),
                name='sm-weigths')
            self.last_b = tf.Variable(tf.constant(
                0.1, shape=[n_classes]), name='sm-biases')
            last_out = tf.add(tf.matmul(last_layer, self.last_W), self.last_b)
            self.layer_nodes.append(last_out)
            self.last_out = last_out
            return last_out

    def get_parameters(self, params, graph=None):
        """Get the parameters of the model.

        :param params: dictionary of keys (str names) and values (tensors).
        :return: evaluated tensors in params
        """
        g = graph if graph is not None else self.tf_graph

        with g.as_default():
            with tf.Session() as self.tf_session:
                self.tf_saver.restore(self.tf_session, self.model_path)
                out = {}
                for par in params:
                    if type(params[par]) == list:
                        for i, p in enumerate(params[par]):
                            out[par + '-' + str(i+1)] = p.eval()
                    else:
                        out[par] = params[par].eval()
                return out
