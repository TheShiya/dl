import torch
from .utils import spatial_argmax
import torch.nn.functional as F


class Planner(torch.nn.Module):
	class Block(torch.nn.Module):
		def __init__(self, n_input, n_output, kernel_size=3, stride=2):
			super().__init__()
			self.c1 = torch.nn.Conv2d(n_input, n_output, kernel_size=kernel_size, padding=kernel_size // 2,
									  stride=stride)
			self.c2 = torch.nn.Conv2d(n_output, n_output, kernel_size=kernel_size, padding=kernel_size // 2)
			self.c3 = torch.nn.Conv2d(n_output, n_output, kernel_size=kernel_size, padding=kernel_size // 2)
			self.skip = torch.nn.Conv2d(n_input, n_output, kernel_size=1, stride=stride)

		def forward(self, x):
			return F.relu(self.c3(F.relu(self.c2(F.relu(self.c1(x)))))) + self.skip(x)
	class UpBlock(torch.nn.Module):
		def __init__(self, n_input, n_output, kernel_size=3, stride=2):
			super().__init__()
			self.c1 = torch.nn.ConvTranspose2d(n_input, n_output, kernel_size=kernel_size, padding=kernel_size // 2,
									  stride=stride, output_padding=1)

		def forward(self, x):
			return F.relu(self.c1(x)) 
#[16, 32, 64, 96, 128]
	def __init__(self, layers=[16, 32, 64, 128], n_output_channels=1, kernel_size=4, use_skip=True):
		super().__init__()
		
		self.batch_norm = torch.nn.BatchNorm2d(3)
		self.device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
		self.resolution = torch.FloatTensor([128, 96]).to(self.device)

		c = 3
		self.use_skip = use_skip
		self.n_conv = len(layers)
		skip_layer_size = [3] + layers[:-1]
		for i, l in enumerate(layers):
			self.add_module('conv%d' % i, self.Block(c, l, kernel_size, 2))
			c = l
		for i, l in list(enumerate(layers))[::-1]:
			self.add_module('upconv%d' % i, self.UpBlock(c, l, kernel_size, 2))
			c = l
			if self.use_skip:
				c += skip_layer_size[i]
		self.classifier = torch.nn.Conv2d(c, n_output_channels, 1)

	def forward(self, x):
		z = self.batch_norm(x)
		up_activation = []
		for i in range(self.n_conv):
			# Add all the information required for skip connections
			up_activation.append(z)
			z = self._modules['conv%d'%i](z)

		for i in reversed(range(self.n_conv)):
			z = self._modules['upconv%d'%i](z)
			# Fix the padding
			z = z[:, :, :up_activation[i].size(2), :up_activation[i].size(3)]
			# Add the skip connection
			if self.use_skip:
				z = torch.cat([z, up_activation[i]], dim=1)

		heatmap = self.classifier(z)
		heatmap = torch.squeeze(heatmap, dim=1)
		aim = spatial_argmax(heatmap)
		aim = (aim + 1)/2 * self.resolution
		return aim
		
	# def __init__(self):
	# 	super().__init__()

	# 	"""
	# 	Your code here
	# 	"""
	# 	raise NotImplementedError('Planner.__init__')

	# def forward(self, img):
	# 	"""
	# 	Your code here
	# 	Predict the aim point in image coordinate, given the supertuxkart image
	# 	@img: (B,3,96,128)
	# 	return (B,2)
	# 	"""
	# 	raise NotImplementedError("Planner.forward")


def save_model(model, suffix=''):
	from torch import save
	from os import path
	if isinstance(model, Planner):
		return save(model.state_dict(), path.join(path.dirname(path.abspath(__file__)), 'planner{}.th'.format(suffix)))
	raise ValueError("model type '%s' not supported!" % str(type(model)))


def load_model():
	from torch import load
	from os import path
	r = Planner()
	r.load_state_dict(load(path.join(path.dirname(path.abspath(__file__)), 'planner.th'), map_location='cpu'))
	return r


if __name__ == '__main__':
	from .controller import control
	from .utils import PyTux
	from argparse import ArgumentParser


	def test_planner(args):
		# Load model
		planner = load_model().eval()
		pytux = PyTux()
		for t in args.track:
			steps = pytux.rollout(t, control, planner=planner, max_frames=1000, verbose=args.verbose)
			print(steps)
		pytux.close()


	parser = ArgumentParser("Test the planner")
	parser.add_argument('track', nargs='+')
	parser.add_argument('-v', '--verbose', action='store_true')
	args = parser.parse_args()
	test_planner(args)
