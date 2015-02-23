from flask import Blueprint, render_template, current_app, abort, g, \
    request, url_for, session, flash, redirect
from galatea.tryton import tryton
from galatea.utils import get_tryton_language
from flask.ext.paginate import Pagination
from flask.ext.babel import gettext as _, lazy_gettext
from flask.ext.mail import Mail, Message
from trytond.config import config as tryton_config
from whoosh import index
from whoosh.qparser import MultifieldParser
import os

blog = Blueprint('blog', __name__, template_folder='templates')

DISPLAY_MSG = lazy_gettext('Displaying <b>{start} - {end}</b> of <b>{total}</b>')

Website = tryton.pool.get('galatea.website')
Post = tryton.pool.get('galatea.blog.post')
Comment = tryton.pool.get('galatea.blog.comment')
User = tryton.pool.get('galatea.user')

GALATEA_WEBSITE = current_app.config.get('TRYTON_GALATEA_SITE')
LIMIT = current_app.config.get('TRYTON_PAGINATION_BLOG_LIMIT', 20)
COMMENTS = current_app.config.get('TRYTON_BLOG_COMMENTS', True)
WHOOSH_MAX_LIMIT = current_app.config.get('WHOOSH_MAX_LIMIT', 500)
BLOG_SCHEMA_PARSE_FIELDS = ['title', 'content']

def _visibility():
    visibility = ['public']
    if session.get('logged_in'):
        visibility.append('register')
    if session.get('manager'):
        visibility.append('manager')
    return visibility

@blog.route("/search/", methods=["GET"], endpoint="search")
@tryton.transaction()
def search(lang):
    '''Search'''
    websites = Website.search([
        ('id', '=', GALATEA_WEBSITE),
        ], limit=1)
    if not websites:
        abort(404)
    website, = websites

    WHOOSH_BLOG_DIR = current_app.config.get('WHOOSH_BLOG_DIR')
    if not WHOOSH_BLOG_DIR:
        abort(404)

    db_name = current_app.config.get('TRYTON_DATABASE')
    locale = get_tryton_language(lang)

    schema_dir = os.path.join(tryton_config.get('database', 'path'),
        db_name, 'whoosh', WHOOSH_BLOG_DIR, locale.lower())

    if not os.path.exists(schema_dir):
        abort(404)

    #breadcumbs
    breadcrumbs = [{
        'slug': url_for('.posts', lang=g.language),
        'name': _('Blog'),
        }, {
        'slug': url_for('.search', lang=g.language),
        'name': _('Search'),
        }]

    q = request.args.get('q')
    if not q:
        return render_template('blog-search.html',
                posts=[],
                breadcrumbs=breadcrumbs,
                pagination=None,
                q=None,
                )

    # Get posts from schema results
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1

    # Search
    ix = index.open_dir(schema_dir)
    query = q.replace('+', ' AND ').replace('-', ' NOT ')
    query = MultifieldParser(BLOG_SCHEMA_PARSE_FIELDS, ix.schema).parse(query)

    with ix.searcher() as s:
        all_results = s.search_page(query, 1, pagelen=WHOOSH_MAX_LIMIT)
        total = all_results.scored_length()
        results = s.search_page(query, page, pagelen=LIMIT) # by pagination
        res = [result.get('id') for result in results]

    domain = [
        ('id', 'in', res),
        ('active', '=', True),
        ('visibility', 'in', _visibility()),
        ]
    order = [('post_create_date', 'DESC'), ('id', 'DESC')]

    posts = Post.search(domain, order=order)

    pagination = Pagination(page=page, total=total, per_page=LIMIT, display_msg=DISPLAY_MSG, bs_version='3')

    return render_template('blog-search.html',
            website=website,
            posts=posts,
            pagination=pagination,
            breadcrumbs=breadcrumbs,
            q=q,
            )

@blog.route("/comment", methods=['POST'], endpoint="comment")
@tryton.transaction()
def comment(lang):
    '''Add Comment'''
    websites = Website.search([
        ('id', '=', GALATEA_WEBSITE),
        ], limit=1)
    if not websites:
        abort(404)
    website, = websites

    post = request.form.get('post')
    comment = request.form.get('comment')

    domain = [
        ('id', '=', post),
        ('active', '=', True),
        ('visibility', 'in', _visibility()),
        ('galatea_website', '=', GALATEA_WEBSITE),
        ]
    posts = Post.search(domain, limit=1)
    if not posts:
        abort(404)
    post, = posts

    if not website.blog_comment:
        flash(_('Not available to publish comments.'), 'danger')
    elif not website.blog_anonymous and not session.get('user'):
        flash(_('Not available to publish comments and anonymous users.' \
            ' Please, login in'), 'danger')
    elif not comment or not post:
        flash(_('Add a comment to publish.'), 'danger')
    else:
        c = Comment()
        c.post = post['id']
        c.user = session['user'] if session.get('user') \
            else website.blog_anonymous_user.id
        c.description = comment
        c.save()
        flash(_('Comment published successfully.'), 'success')

        mail = Mail(current_app)

        mail_to = current_app.config.get('DEFAULT_MAIL_SENDER')
        subject =  '%s - %s' % (current_app.config.get('TITLE'), _('New comment published'))
        msg = Message(subject,
                body = render_template('emails/blog-comment-text.jinja', post=post, comment=comment),
                html = render_template('emails/blog-comment-html.jinja', post=post, comment=comment),
                sender = mail_to,
                recipients = [mail_to])
        mail.send(msg)

    return redirect(url_for('.post', lang=g.language, slug=post['slug']))

@blog.route("/<slug>", endpoint="post")
@tryton.transaction()
def post(lang, slug):
    '''Post detaill'''
    websites = Website.search([
        ('id', '=', GALATEA_WEBSITE),
        ], limit=1)
    if not websites:
        abort(404)
    website, = websites

    posts = Post.search([
        ('slug', '=', slug),
        ('active', '=', True),
        ('visibility', 'in', _visibility()),
        ('galatea_website', '=', GALATEA_WEBSITE),
        ], limit=1)

    if not posts:
        abort(404)
    post, = posts

    breadcrumbs = [{
        'slug': url_for('.posts', lang=g.language),
        'name': _('Blog'),
        }, {
        'slug': url_for('.post', lang=g.language, slug=post.slug),
        'name': post.name,
        }]

    return render_template('blog-post.html',
            website=website,
            post=post,
            breadcrumbs=breadcrumbs,
            )

@blog.route("/key/<key>", endpoint="key")
@tryton.transaction()
def key(lang, key):
    '''Posts by Key'''
    websites = Website.search([
        ('id', '=', GALATEA_WEBSITE),
        ], limit=1)
    if not websites:
        abort(404)
    website, = websites

    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1

    domain = [
        ('metakeywords', 'ilike', '%'+key+'%'),
        ('active', '=', True),
        ('visibility', 'in', _visibility()),
        ('galatea_website', '=', GALATEA_WEBSITE),
        ]
    total = Post.search_count(domain)
    offset = (page-1)*LIMIT

    order = [('post_create_date', 'DESC'), ('id', 'DESC')]
    posts = Post.search(domain, offset, LIMIT, order)

    pagination = Pagination(page=page, total=total, per_page=LIMIT, display_msg=DISPLAY_MSG, bs_version='3')

    #breadcumbs
    breadcrumbs = [{
        'slug': url_for('.posts', lang=g.language),
        'name': _('Blog'),
        }, {
        'slug': url_for('.key', lang=g.language, key=key),
        'name': key,
        }]

    return render_template('blog-key.html',
            website=website,
            posts=posts,
            pagination=pagination,
            breadcrumbs=breadcrumbs,
            key=key,
            )

@blog.route("/user/<user>", endpoint="user")
@tryton.transaction()
def users(lang, user):
    '''Posts by User'''
    websites = Website.search([
        ('id', '=', GALATEA_WEBSITE),
        ], limit=1)
    if not websites:
        abort(404)
    website, = websites

    try:
        user = int(user)
    except:
        abort(404)

    users = User.search([
        ('id', '=', user)
        ], limit=1)
    if not users:
        abort(404)
    user, = users

    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1

    domain = [
        ('user', '=', user.id),
        ('active', '=', True),
        ('visibility', 'in', _visibility()),
        ('galatea_website', '=', GALATEA_WEBSITE),
        ]
    total = Post.search_count(domain)
    offset = (page-1)*LIMIT

    if not total:
        abort(404)

    order = [('post_create_date', 'DESC'), ('id', 'DESC')]
    posts = Post.search(domain, offset, LIMIT, order)

    pagination = Pagination(page=page, total=total, per_page=LIMIT, display_msg=DISPLAY_MSG, bs_version='3')

    #breadcumbs
    breadcrumbs = [{
        'slug': url_for('.posts', lang=g.language),
        'name': _('Blog'),
        }, {
        'slug': url_for('.user', lang=g.language, user=user.id),
        'name': user.rec_name,
        }]

    return render_template('blog-user.html',
            website=website,
            posts=posts,
            user=user,
            pagination=pagination,
            breadcrumbs=breadcrumbs,
            )

@blog.route("/", endpoint="posts")
@tryton.transaction()
def posts(lang):
    '''Posts'''
    websites = Website.search([
        ('id', '=', GALATEA_WEBSITE),
        ], limit=1)
    if not websites:
        abort(404)
    website, = websites

    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1

    domain = [
        ('active', '=', True),
        ('visibility', 'in', _visibility()),
        ('galatea_website', '=', GALATEA_WEBSITE),
        ]
    total = Post.search_count(domain)
    offset = (page-1)*LIMIT

    order = [('post_create_date', 'DESC'), ('id', 'DESC')]
    posts = Post.search(domain, offset, LIMIT, order)

    pagination = Pagination(page=page, total=total, per_page=LIMIT, display_msg=DISPLAY_MSG, bs_version='3')

    #breadcumbs
    breadcrumbs = [{
        'slug': url_for('.posts', lang=g.language),
        'name': _('Blog'),
        }]

    return render_template('blog.html',
            website=website,
            posts=posts,
            pagination=pagination,
            breadcrumbs=breadcrumbs,
            )
