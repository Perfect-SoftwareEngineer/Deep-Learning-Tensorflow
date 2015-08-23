from sklearn.linear_model import LogisticRegression

from gaussian_rbm import GaussianRBM


class ClsGaussianRBM(object):

    def __init__(self,
                 num_visible,
                 num_hidden):

        # standard restricted boltzmann machine object
        self.grbm = GaussianRBM(num_visible,
                                num_hidden)

        # Logistic Regression classifier on top of the spline rbm
        self.cls = LogisticRegression()

    def learn_unsupervised_features(self,
                                    data,
                                    validation=None,
                                    max_epochs=100,
                                    batch_size=1,
                                    alpha=0.1,
                                    m=0.5,
                                    gibbs_k=1,
                                    verbose=False,
                                    display=None):
        self.grbm.train(data,
                        validation=validation,
                        max_epochs=max_epochs,
                        batch_size=batch_size,
                        alpha=alpha,
                        m=m,
                        gibbs_k=gibbs_k,
                        verbose=verbose,
                        display=display)

    def fit_logistic_cls(self, data, labels):
        """Train a logistic regression classifier on top of the learned features
        by the Restricted Boltzmann Machine.
        """
        (data_probs, data_states) = self.grbm.sample_hidden_from_visible(data)
        self.cls.fit(data_probs, labels)

    def predict_logistic_cls(self, data):
        """Predict the labels for data using the Logistic Regression layer on top of the
        learned features by the Restricted Boltzmann Machine.
        """
        (data_probs, data_states) = self.grbm.sample_hidden_from_visible(X_test)
        return self.cls.predict(data_probs)
