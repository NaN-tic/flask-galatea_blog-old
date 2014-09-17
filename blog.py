from flask import Blueprint, render_template, current_app, abort, g, \
    request, url_for, session, flash, redirect
from galatea.tryton import tryton
from flask.ext.paginate import Pagination
from flask.ext.babel import gettext as _, lazy_gettext as __
from flask.ext.mail import Mail, Message

blog = Blueprint('blog', __name__, template_folder='templates')

DISPLAY_MSG = __('Displaying <b>{start} - {end}</b> {record_name} of <b>{total}</b>')

Post = tryton.pool.get('galatea.blog.post')
Comment = tryton.pool.get('galatea.blog.comment')
User = tryton.pool.get('res.user')

GALATEA_WEBSITE = current_app.config.get('TRYTON_GALATEA_SITE')
LIMIT = current_app.config.get('TRYTON_PAGINATION_BLOG_LIMIT', 20)
COMMENTS = current_app.config.get('TRYTON_BLOG_COMMENTS', True)

POST_FIELD_NAMES = ['name', 'slug', 'description', 'comment', 'comments',
    'metakeywords', 'create_uid', 'create_uid.name', 'post_create_date']

@blog.route("/comment", methods=['POST'], endpoint="comment")
@tryton.transaction()
def comment(lang):
    '''Add Comment'''
    post = request.form.get('post')
    comment = request.form.get('comment')

    domain = [
        ('id', '=', post),
        ('active', '=', True),
        ('galatea_website', '=', GALATEA_WEBSITE),
        ]
    posts = Post.search_read(domain, limit=1, fields_names=POST_FIELD_NAMES)
    if not posts:
        abort(404)
    post, = posts

    if not COMMENTS:
        flash(_('Not available to publish comments.'), 'danger')
    elif not session.get('user'):
        flash(_('Loging to publish comments.'), 'danger')
    elif not comment or not post:
        flash(_('Add a comment to publish.'), 'danger')
    else:
        Comment.create([{
            'post': post['id'],
            'user': session['user'],
            'description': comment,
            }])
        flash(_('Comment published successfully.'), 'success')

        mail = Mail(current_app)

        mail_to = current_app.config.get('DEFAULT_MAIL_SENDER')
        subject =  '%s - %s' % (current_app.config.get('TITLE'), _('New comment published'))
        msg = Message(subject,
                body = render_template('emails/blog-comment-text.jinja', post=post),
                html = render_template('emails/blog-comment-html.jinja', post=post),
                sender = mail_to,
                recipients = [mail_to])
        mail.send(msg)

    return redirect(url_for('.post', lang=g.language, slug=post['slug']))

@blog.route("/<slug>", endpoint="post")
@tryton.transaction()
def post(lang, slug):
    '''Post detaill'''
    posts = Post.search([
        ('slug', '=', slug),
        ('active', '=', True),
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
            post=post,
            breadcrumbs=breadcrumbs,
            cache_prefix='blog-post-%s-%s' % (post.id, lang),
            )

@blog.route("/key/<key>", endpoint="key")
@tryton.transaction()
def keys(lang, key):
    '''Posts by Key'''
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1

    domain = [
        ('active', '=', True),
        ('galatea_website', '=', GALATEA_WEBSITE),
        ('metakeywords', 'ilike', '%'+key+'%'),
        ]
    total = Post.search_count(domain)
    offset = (page-1)*LIMIT

    order = [('create_date', 'DESC'), ('id', 'DESC')]
    posts = Post.search_read(domain, offset, LIMIT, order, POST_FIELD_NAMES)

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
            posts=posts,
            pagination=pagination,
            breadcrumbs=breadcrumbs,
            cache_prefix='blog-post-key-%s-%s-%s' % (lang, key, page),
            )

@blog.route("/user/<user>", endpoint="user")
@tryton.transaction()
def users(lang, user):
    '''Posts by User'''
    try:
        user = int(user)
    except:
        abort(404)

    domain = [
        ('active', '=', True),
        ('create_uid', '=', user),
        ('galatea_website', '=', GALATEA_WEBSITE),
        ]
    total = Post.search_count(domain)
    if not total:
        abort(404)

    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1

    domain = [
        ('active', '=', True),
        ('create_uid', '=', user),
        ('galatea_website', '=', GALATEA_WEBSITE),
        ]
    total = Post.search_count(domain)
    offset = (page-1)*LIMIT

    order = [('create_date', 'DESC'), ('id', 'DESC')]
    posts = Post.search_read(domain, offset, LIMIT, order, POST_FIELD_NAMES)

    user = User(user)

    pagination = Pagination(page=page, total=total, per_page=LIMIT, display_msg=DISPLAY_MSG, bs_version='3')

    #breadcumbs
    breadcrumbs = [{
        'slug': url_for('.posts', lang=g.language),
        'name': _('Blog'),
        }, {
        'slug': url_for('.user', lang=g.language, user=user),
        'name': user.name,
        }]

    return render_template('blog-user.html',
            posts=posts,
            user=user,
            pagination=pagination,
            breadcrumbs=breadcrumbs,
            cache_prefix='blog-post-user-%s-%s-%s' % (lang, user, page),
            )

@blog.route("/", endpoint="posts")
@tryton.transaction()
def posts(lang):
    '''Posts'''
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1

    domain = [
        ('active', '=', True),
        ('galatea_website', '=', GALATEA_WEBSITE),
        ]
    total = Post.search_count(domain)
    offset = (page-1)*LIMIT

    order = [('create_date', 'DESC'), ('id', 'DESC')]
    posts = Post.search_read(domain, offset, LIMIT, order, POST_FIELD_NAMES)

    pagination = Pagination(page=page, total=total, per_page=LIMIT, display_msg=DISPLAY_MSG, bs_version='3')

    #breadcumbs
    breadcrumbs = [{
        'slug': url_for('.posts', lang=g.language),
        'name': _('Blog'),
        }]

    return render_template('blog.html',
            posts=posts,
            pagination=pagination,
            breadcrumbs=breadcrumbs,
            cache_prefix='blog-post-all-%s-%s' % (lang, page),
            )
