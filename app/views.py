from flask import render_template, redirect, url_for, request, session, jsonify, make_response, flash

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, IntegerField, FloatField, SubmitField
from wtforms.validators import InputRequired, Email, Length, NumberRange
from flask_login import login_user, logout_user, login_required, current_user

from app import app, db, login_manager
from .models import *

## Machine Learning 
from .movie_ai import *
import heapq
import random
from urllib import request
from bs4 import BeautifulSoup

COUNTER = 0

NO_OF_RATINGS_TO_TRIGGER_ALGORITHM = 2
NUM_OF_MOVIES_TO_USE = 10
NUM_OF_MOVIES_TO_RECOMMEND = 10
IMDB_URL_STRING = 'http://www.imdb.com/title/tt'
MAX_SEARCH_RESULTS = 5

@login_manager.user_loader
def load_user(user_id):
	return User.query.get(int(user_id))


class LoginForm(FlaskForm):
	username = StringField('Username', validators=[InputRequired(), Length(min=4, max=42)])
	password = PasswordField('Password', validators=[InputRequired(), Length(min=4, max=42)])
	remember = BooleanField('Remember me')

class RegisterForm(FlaskForm):
	email = StringField('Email', validators=[InputRequired(), Email(message='Invalid Email'), Length(max=42)])
	username = StringField('Username', validators=[InputRequired(), Length(min=4, max=42)])
	password = PasswordField('Password', validators=[InputRequired(), Length(min=4, max=42)])

class PreferenceForm(FlaskForm):
	comedy = FloatField('Comedy', validators=[InputRequired(), NumberRange(min=-5, max=5)])
	action = FloatField('Action', validators=[InputRequired(), NumberRange(min=-5, max=5)])
	romance = FloatField('Romance', validators=[InputRequired(), NumberRange(min=-5, max=5)])
	scifi = FloatField('Scifi', validators=[InputRequired(), NumberRange(min=-5, max=5)])

class SearchForm(FlaskForm):
	search = StringField('search', validators=[InputRequired()])
	submit = SubmitField('Search', render_kw={'class': 'btn btn-success btn-block'})


class RatingForm(FlaskForm):
	rating = IntegerField('Rating', validators=[InputRequired()])

def random_preference():
	choices = [-5., -4., -3., -2., -1., 0., 1., 2., 3., 4., 5.]
	return random.choice(choices)

def get_poster_and_description(imdb_id):
	url = IMDB_URL_STRING + str(imdb_id)
	soup = BeautifulSoup(request.urlopen(url).read(), "lxml")
	image_link = soup.find(itemprop="image")
	description = soup.find(itemprop="description").text
	return image_link.get("src"), description


@app.route('/')
@login_required
def home():
	movies = Movie.query.limit(NUM_OF_MOVIES_TO_RECOMMEND)
	### Get the images link
	movies_with_poster_images = []
	for movie in movies:
		imdb_id = movie.imdb_id
		image_link, description = get_poster_and_description(imdb_id)
		movie_with_image = (movie, image_link, description)
		movies_with_poster_images.append(movie_with_image)

	return render_template('home.html', movies=movies_with_poster_images)


@app.route('/login', methods=['GET', 'POST'])
def login():
	form = LoginForm()
	
	if form.validate_on_submit():
		user = User.query.filter_by(username=form.username.data).first()
		if user:
			if user.password == form.password.data:
				login_user(user, remember=form.remember.data)
				return redirect(url_for('dashboard'))
	
	return render_template('login.html', form=form)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
	form = RegisterForm()

	if form.validate_on_submit():
		user = User.query.filter_by(username=form.username.data).first()
		if form.username.data == user: 
			flash('The username is already taken! Please Make another choice.')
			return redirect(url_for('signup'))
		new_user = User(form.username.data, form.password.data)
		comedy = random_preference()
		action = random_preference()
		romance = random_preference()
		scifi = random_preference()
		db.session.add(new_user)
		prefer = Preference(user_id=new_user.id, comedy=comedy, action=action, romance=romance, scifi=scifi)
		db.session.add(prefer)
		db.session.commit()
		login_user(new_user, remember=True)
		flash('Thanks for registering')
		return redirect(url_for('setpreferences'))

	return render_template('signup.html', form=form)

@app.route('/secret')	
def secret():
	return render_template('secret.html')


@app.route('/about')	
def about():
	return render_template('about.html')
	
@app.route('/setpreferences', methods=['POST', 'GET'])
@login_required
def setpreferences():
	form = PreferenceForm()
	if form.validate_on_submit():
		user_id = current_user.id
		preference = Preference.query.filter_by(user_id = current_user.id).first()
	
		comedy = float(form.comedy.data) / 5.
		action = float(form.action.data) / 5.
		romance = float(form.romance.data) / 5.
		scifi = float(form.scifi.data) / 5.

		comedy, action, romance, scifi = limit(comedy), limit(action), limit(romance), limit(scifi)

		if preference:
			preference.comedy = comedy
			preference.action = action
			preference.romance = romance
			preference.scifi = scifi
		else:
			preference = Preference(user_id=user_id, comedy=comedy, action=action, romance=romance, scifi=scifi)
		db.session.add(preference)
		db.session.commit()
		return redirect(url_for('dashboard'))
	preference = Preference.query.filter_by(user_id = current_user.id).first()
	return render_template('setpreferences.html', preference = preference, form=form)


@app.route('/dashboard')
@login_required
def dashboard():
	### Get the BEST 10 predicted rated movies
	movies = []
	for movie in Movie.query.limit(NUM_OF_MOVIES_TO_USE):
		predicted_rating = calculate_predicted_rating(current_user, movie)
		mr = (movie, predicted_rating)
		movies.append(mr)
	
	movies = heapq.nlargest(NUM_OF_MOVIES_TO_RECOMMEND, movies, lambda mr: mr[1])
	### Get the images link
	movies_with_poster_images = []
	for mr in movies:
		movie = mr[0]
		imdb_id = movie.imdb_id
		image_link, description = get_poster_and_description(imdb_id)
		mr_with_image = mr + (image_link, description)
		movies_with_poster_images.append(mr_with_image)

	return render_template('dashboard.html', username=current_user.username, movies=movies_with_poster_images)


@app.route('/rate/<int:movie_id>', methods=['GET', 'POST'])
@login_required
def rate(movie_id):
	global COUNTER

	user_id = current_user.id
	# get user's rating for this movie
	form = RatingForm()
	if form.validate_on_submit():
		rating = int(form.rating.data)
		# update the ratings table and add the rating
		query = ratings.insert().values(user_id=user_id, movie_id=movie_id, rating=rating)
		db.session.execute(query)
		db.session.commit()

		COUNTER = COUNTER + 1
		### Perform Machine Learning if 10 ratings have been made
		if COUNTER % NO_OF_RATINGS_TO_TRIGGER_ALGORITHM == 0:
			update_user_preferences(current_user)
		
		return redirect(url_for('dashboard'))

	movie = Movie.query.get(movie_id)
	return render_template('rate.html', movie=movie, form=form)

# @app.route('/search', methods=['GET', 'POST'])
# @login_required
# def search():
#   form = SearchForm(request.form)
#   if request.method == 'POST' and form.validate_on_submit():
#   		return redirect((url_for('search_results', query=form.search.data, form=form)))


# @app.route('/search_results/<query>')
# @login_required
# def search_results(query, form):
#   results = Movie.query.whoosh_search(query, MAX_SEARCH_RESULTS).all()
#   return render_template('search_results.html', query=query, results=results)


@app.route('/logout')
@login_required
def logout():
	logout_user()
	return redirect(url_for('home'))

#########################
### JSON API STUFF #####
#########################

# movies = [
#     {
#         'name': 'All esper dayo',
#     },
#     {
#         'name': 'Dr Strange'
#     },
#     {
#         'name': 'Hell Boy'
#     },
#     {
#         'name': 'Hell Boy'
#     },
#     {
#         'name': 'Hell Boy'
#     },
#     {
#         'name': 'Hell Boy'
#     },
#     {
#         'name': 'Hell Boy'
#     },
#     {
#         'name': 'Hell Boy'
#     },
#     {
#         'name': 'Hell Boy'
#     },
#     {
#         'name': 'Hell Boy'
#     }
# ]

@app.route('/api/dashboard', methods=['GET'])
def get_movies():
	movies = Movie.query.limit(50)
	movies = [movie.serialize for movie in movies]
	return jsonify({'movies': movies})


@app.route('/api/signup', methods=['POST'])
def mobile_signup():
	username = request.args.get('username')
	password = request.args.get('password')
	if username and password:
		prev_user = User.query.filter_by(username=username).first()
		if not prev_user:
			new_user = User(username, password)
			db.session.add(new_user)
			db.session.commit()
			comedy = random.random() * 2 - 1
			action = random.random() * 2 - 1
			romance = random.random() * 2 - 1
			scifi = random.random() * 2 - 1
			prefer = Preference(user_id=new_user.id, comedy=comedy, action=action, romance=romance, scifi=scifi)
			db.session.add(prefer)
			db.session.commit()
			return make_response(jsonify({'welcome': 'Welcome to the Secret Project'}), 201)
	
	return make_response(jsonify({'error': 'You wrong boy'}), 400)

@app.route('/api/login', methods=['GET'])
def mobile_login():
	username = request.args.get('username')
	password = request.args.get('password')
	if username and password:
		## check if there is a user
		user = User.query.filter_by(username=username).first()
		if user and user.password == password:
			## login the user 
			## not really logging in, but giving some secret code or something or just dashboard page data 
			movies = []
			for movie in Movie.query.all():
				predicted_rating = calculate_predicted_rating(user, movie)
				mr = (movie.serialize, predicted_rating)
				movies.append(mr)
			movies = heapq.nlargest(30, movies, lambda mr: mr[1])
		
			return jsonify({'movies': movies}),  200

	return make_response(jsonify({'error': 'Wrong username or password'}), 400)



@app.route('/api/rate/<int:movie_id>', methods=['GET', 'POST'])
def mobile_rate(movie_id):
	
	movie = Movie.query.get(movie_id)
	return jsonify({'movie': movie.serialize}), 200